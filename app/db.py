import json
import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


def get_connection() -> psycopg.Connection:
    """Ouvre une connexion PostgreSQL dont les lignes se lisent comme des dictionnaires.

    Lit DATABASE_URL/DATABASE_SCHEMA à l'appel plutôt qu'au chargement du module : ce module
    est importé très tôt (via app.tools) par des modules qui n'ont pas encore forcément
    appelé load_dotenv(), une constante figée au niveau module resterait vide en permanence.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL manquante (voir .env.example)")

    conn = psycopg.connect(database_url, row_factory=dict_row)
    database_schema = os.environ.get("DATABASE_SCHEMA", "public")
    if database_schema != "public":
        schema = sql.Identifier(database_schema)
        conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema))
        conn.execute(sql.SQL("SET search_path TO {}").format(schema))
        conn.commit()
    return conn


def init_db() -> None:
    """Crée le schéma PostgreSQL complet sur une base vide, sans dépendre de SQLite."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY,
            user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            user_request TEXT NOT NULL,
            agent_response TEXT,
            metrics_json TEXT,
            status TEXT NOT NULL CHECK (status IN ('processing', 'pending', 'completed', 'error')),
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_plans_user_created
        ON plans (user_id, created_at DESC)
        """,
        """
        CREATE TABLE IF NOT EXISTS issues (
            id BIGSERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            assignee TEXT NOT NULL,
            due_date DATE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS records (
            id BIGSERIAL PRIMARY KEY,
            record_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS calendar_events (
            id BIGSERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            start TIMESTAMPTZ NOT NULL,
            duration_min INTEGER NOT NULL CHECK (duration_min > 0),
            attendees_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS actions (
            id BIGSERIAL PRIMARY KEY,
            plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
            action_index INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            input_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('pending', 'executing', 'executed', 'rejected', 'error', 'cancelled')
            ),
            idempotency_key TEXT UNIQUE NOT NULL,
            output_json TEXT,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            UNIQUE (plan_id, action_index)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_actions_plan_status
        ON actions (plan_id, status)
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id BIGSERIAL PRIMARY KEY,
            idempotency_key TEXT UNIQUE NOT NULL,
            tool_name TEXT NOT NULL,
            input_json TEXT NOT NULL,
            output_json TEXT,
            status TEXT NOT NULL,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_sessions_token
        ON sessions (token_hash, expires_at)
        """,
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            plan_id TEXT REFERENCES plans(id) ON DELETE SET NULL,
            user_message TEXT NOT NULL,
            agent_response TEXT NOT NULL,
            metrics_json TEXT,
            created_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_user_created
        ON conversations (user_id, created_at DESC)
        """,
        """
        CREATE TABLE IF NOT EXISTS action_owners (
            action_id BIGINT PRIMARY KEY REFERENCES actions(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            hidden_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL
        )
        """,
        "ALTER TABLE action_owners ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ",
        """
        CREATE INDEX IF NOT EXISTS idx_action_owners_user
        ON action_owners (user_id, created_at DESC)
        """,
    ]

    conn = get_connection()
    try:
        for statement in statements:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def database_is_ready() -> bool:
    """Vérifie que PostgreSQL répond à une requête minimale."""
    try:
        conn = get_connection()
        try:
            conn.execute("SELECT 1").fetchone()
            return True
        finally:
            conn.close()
    except (psycopg.Error, RuntimeError):
        return False


def get_recent_audit_log(
    limit: int = 20,
    *,
    user_id: int | None = None,
    plan_ids: list[str] | None = None,
) -> list[dict]:
    """Retourne le journal visible par un compte ou par des plans anonymes connus."""
    safe_limit = max(1, min(limit, 100))
    safe_plan_ids = list(dict.fromkeys(plan_ids or []))[:50]
    if user_id is None and not safe_plan_ids:
        return []

    conn = get_connection()
    try:
        if user_id is not None:
            rows = conn.execute(
                """
                SELECT audit_log.id, audit_log.idempotency_key, audit_log.tool_name,
                       audit_log.input_json, audit_log.output_json, audit_log.status,
                       audit_log.error, audit_log.created_at,
                       actions.id AS action_id, actions.plan_id,
                       actions.status AS action_status
                FROM audit_log
                JOIN actions ON actions.idempotency_key = audit_log.idempotency_key
                JOIN action_owners ON action_owners.action_id = actions.id
                WHERE action_owners.user_id = %s
                ORDER BY audit_log.created_at DESC
                LIMIT %s
                """,
                (user_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT audit_log.id, audit_log.idempotency_key, audit_log.tool_name,
                       audit_log.input_json, audit_log.output_json, audit_log.status,
                       audit_log.error, audit_log.created_at,
                       actions.id AS action_id, actions.plan_id,
                       actions.status AS action_status
                FROM audit_log
                JOIN actions ON actions.idempotency_key = audit_log.idempotency_key
                JOIN plans ON plans.id = actions.plan_id
                WHERE plans.user_id IS NULL
                  AND actions.plan_id = ANY(%s::text[])
                ORDER BY audit_log.created_at DESC
                LIMIT %s
                """,
                (safe_plan_ids, safe_limit),
            ).fetchall()
    finally:
        conn.close()

    calls = []
    for row in rows:
        item = dict(row)
        item["input"] = json.loads(item.pop("input_json"))
        output_json = item.pop("output_json")
        item["output"] = json.loads(output_json) if output_json else None
        calls.append(item)
    return calls
