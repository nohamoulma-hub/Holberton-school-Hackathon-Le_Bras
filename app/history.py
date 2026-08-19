import json
from datetime import datetime, timezone
from typing import Any

from app.db import get_connection


def save_conversation(user_id: int, message: str, agent_result: dict[str, Any]) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO conversations
                (user_id, plan_id, user_message, agent_response, metrics_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                agent_result.get("plan_id"),
                message,
                agent_result.get("response", ""),
                json.dumps(agent_result.get("metrics"), ensure_ascii=False),
                datetime.now(timezone.utc),
            ),
        )
        conversation_id = cursor.fetchone()["id"]
        conn.commit()
        return conversation_id
    finally:
        conn.close()


def link_actions_to_user(user_id: int, trace: list[dict[str, Any]]) -> None:
    action_ids = {
        step.get("action_id") or (step.get("output") or {}).get("action_id")
        for step in trace
        if isinstance(step, dict)
    }
    action_ids.discard(None)
    if not action_ids:
        return
    created_at = datetime.now(timezone.utc)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO action_owners (action_id, user_id, created_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (action_id) DO NOTHING
                """,
                [(action_id, user_id, created_at) for action_id in action_ids],
            )
        conn.commit()
    finally:
        conn.close()


def list_conversations(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 100))
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, plan_id, user_message, agent_response, metrics_json, created_at
            FROM conversations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, safe_limit),
        ).fetchall()
    finally:
        conn.close()
    conversations = []
    for row in rows:
        item = dict(row)
        item["metrics"] = json.loads(item.pop("metrics_json")) if item["metrics_json"] else None
        conversations.append(item)
    return conversations


def list_accepted_actions(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 100))
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT actions.id, actions.plan_id, actions.tool_name, actions.input_json,
                   actions.output_json, actions.status, actions.created_at, actions.updated_at
            FROM action_owners
            JOIN actions ON actions.id = action_owners.action_id
            WHERE action_owners.user_id = %s AND actions.status = 'executed'
            ORDER BY actions.updated_at DESC
            LIMIT %s
            """,
            (user_id, safe_limit),
        ).fetchall()
    finally:
        conn.close()
    actions = []
    for row in rows:
        item = dict(row)
        item["input"] = json.loads(item.pop("input_json"))
        item["output"] = json.loads(item.pop("output_json")) if item["output_json"] else None
        actions.append(item)
    return actions
