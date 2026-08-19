import json
from datetime import datetime, timezone
from typing import Any

from app.db import get_connection


def create_plan(plan_id: str, user_request: str, user_id: int | None = None) -> None:
    """Crée le plan avant tout appel d'outil et conserve la demande d'origine."""
    now = datetime.now(timezone.utc)
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO plans
                (id, user_id, user_request, status, created_at, updated_at)
            VALUES (%s, %s, %s, 'processing', %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                user_request = CASE
                    WHEN plans.user_request = '' THEN EXCLUDED.user_request
                    ELSE plans.user_request
                END,
                user_id = COALESCE(plans.user_id, EXCLUDED.user_id),
                updated_at = EXCLUDED.updated_at
            """,
            (plan_id, user_id, user_request, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def ensure_plan(plan_id: str) -> None:
    """Garantit le parent d'une action créée hors de la boucle Agent, notamment en test."""
    create_plan(plan_id, "")


def assign_plan_to_user(plan_id: str, user_id: int) -> None:
    """Rattache un plan anonyme au compte connecté après la réponse de l'Agent."""
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE plans
            SET user_id = COALESCE(user_id, %s), updated_at = %s
            WHERE id = %s
            """,
            (user_id, datetime.now(timezone.utc), plan_id),
        )
        conn.commit()
    finally:
        conn.close()


def refresh_plan_status(plan_id: str) -> str:
    """Calcule le statut du plan depuis les statuts persistants de ses actions."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT status FROM actions WHERE plan_id = %s",
            (plan_id,),
        ).fetchall()
        statuses = {row["status"] for row in rows}
        if "pending" in statuses or "executing" in statuses:
            status = "pending"
        elif "error" in statuses:
            status = "error"
        else:
            status = "completed"
        conn.execute(
            "UPDATE plans SET status = %s, updated_at = %s WHERE id = %s",
            (status, datetime.now(timezone.utc), plan_id),
        )
        conn.commit()
        return status
    finally:
        conn.close()


def finalize_plan(plan_id: str, response: str, metrics: dict[str, Any]) -> None:
    """Enregistre la réponse finale et rend le plan restaurable après rechargement."""
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE plans
            SET agent_response = %s, metrics_json = %s, updated_at = %s
            WHERE id = %s
            """,
            (
                response,
                json.dumps(metrics, ensure_ascii=False),
                datetime.now(timezone.utc),
                plan_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    refresh_plan_status(plan_id)


def _decode_json(value: str | None) -> Any:
    return json.loads(value) if value else None


def get_plan(plan_id: str) -> dict[str, Any] | None:
    """Reconstruit un plan et ses actions dans l'ordre d'origine."""
    conn = get_connection()
    try:
        plan = conn.execute(
            """
            SELECT id, user_id, user_request, agent_response, metrics_json, status,
                   created_at, updated_at
            FROM plans
            WHERE id = %s
            """,
            (plan_id,),
        ).fetchone()
        if plan is None:
            return None
        rows = conn.execute(
            """
            SELECT id, action_index, tool_name, input_json, status, output_json, error,
                   created_at, updated_at
            FROM actions
            WHERE plan_id = %s
            ORDER BY action_index, id
            """,
            (plan_id,),
        ).fetchall()
    finally:
        conn.close()

    actions = []
    for row in rows:
        action = dict(row)
        action["action_id"] = action.pop("id")
        action["tool"] = action.pop("tool_name")
        action["input"] = _decode_json(action.pop("input_json")) or {}
        action["output"] = _decode_json(action.pop("output_json"))
        actions.append(action)

    item = dict(plan)
    item["plan_id"] = item.pop("id")
    item["response"] = item.pop("agent_response") or ""
    item["metrics"] = _decode_json(item.pop("metrics_json"))
    item["actions"] = actions
    return item


def get_latest_user_plan(user_id: int) -> dict[str, Any] | None:
    """Retourne le dernier plan d'un compte, puis le reconstruit complètement."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT id
            FROM plans
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    return get_plan(row["id"]) if row else None
