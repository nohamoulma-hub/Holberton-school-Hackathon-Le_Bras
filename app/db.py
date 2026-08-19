import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


DATABASE_URL = os.environ.get("DATABASE_URL", "")
DATABASE_SCHEMA = os.environ.get("DATABASE_SCHEMA", "public")


def get_connection() -> psycopg.Connection:
    """Ouvre une connexion PostgreSQL dont les lignes se lisent comme des dictionnaires."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL manquante (voir .env.example)")

    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    if DATABASE_SCHEMA != "public":
        schema = sql.Identifier(DATABASE_SCHEMA)
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
            created_at TIMESTAMPTZ NOT NULL
        )
        """,
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


def get_recent_audit_log(limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(limit, 100))
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, idempotency_key, tool_name, input_json, output_json, status, error,
                   created_at
            FROM audit_log
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (safe_limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
