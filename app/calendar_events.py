import json
import os
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db import get_connection
from app.plans import refresh_plan_status


DEFAULT_TIMEZONE = "Europe/Paris"


def _application_timezone() -> ZoneInfo:
    timezone_name = os.environ.get("APP_TIMEZONE", DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Fuseau horaire APP_TIMEZONE invalide : {timezone_name}") from exc


def list_calendar_events(
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    user_id: int | None = None,
    plan_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Liste uniquement les événements du compte ou des plans anonymes du navigateur."""
    if start_date and end_date and end_date <= start_date:
        raise ValueError("La date de fin doit être postérieure à la date de début")

    anonymous_plan_ids = list(dict.fromkeys(plan_ids or []))[:50]
    if user_id is None and not anonymous_plan_ids:
        return []

    timezone = _application_timezone()
    filters = []
    parameters: list[Any] = []
    if user_id is not None:
        filters.append("action_owners.user_id = %s")
        parameters.append(user_id)
    else:
        filters.append("actions.plan_id = ANY(%s)")
        filters.append("action_owners.action_id IS NULL")
        parameters.append(anonymous_plan_ids)
    if start_date:
        filters.append("calendar_events.start >= %s")
        parameters.append(datetime.combine(start_date, time.min, timezone))
    if end_date:
        filters.append("calendar_events.start < %s")
        parameters.append(datetime.combine(end_date, time.min, timezone))

    where_clause = f"WHERE {' AND '.join(filters)}"
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT calendar_events.id, calendar_events.title, calendar_events.start,
                   calendar_events.duration_min, calendar_events.attendees_json,
                   actions.id AS action_id, actions.plan_id
            FROM calendar_events
            JOIN actions
              ON actions.tool_name = 'create_calendar_event'
             AND actions.status = 'executed'
             AND (actions.output_json::jsonb ->> 'event_id')::BIGINT = calendar_events.id
            LEFT JOIN action_owners ON action_owners.action_id = actions.id
            {where_clause}
            ORDER BY calendar_events.start, calendar_events.id
            LIMIT 500
            """,
            tuple(parameters),
        ).fetchall()
    finally:
        conn.close()

    events = []
    for row in rows:
        attendees = json.loads(row["attendees_json"])
        events.append(
            {
                "id": row["id"],
                "title": row["title"],
                "start": row["start"].astimezone(timezone).isoformat(),
                "duration_min": row["duration_min"],
                "attendees": attendees if isinstance(attendees, list) else [],
                "action_id": row["action_id"],
                "plan_id": row["plan_id"],
            }
        )
    return events


def delete_calendar_event(
    event_id: int,
    *,
    user_id: int | None = None,
    plan_id: str | None = None,
) -> dict[str, Any]:
    """Supprime un événement seulement si le compte ou le navigateur en est propriétaire."""
    if user_id is None and not plan_id:
        raise ValueError(f"Événement introuvable : {event_id}")

    conn = get_connection()
    try:
        ownership_filter = (
            "action_owners.user_id = %s"
            if user_id is not None
            else "actions.plan_id = %s AND action_owners.action_id IS NULL"
        )
        owner_parameter = user_id if user_id is not None else plan_id
        event = conn.execute(
            f"""
            SELECT calendar_events.id, calendar_events.title, actions.id AS action_id,
                   actions.plan_id, actions.idempotency_key
            FROM calendar_events
            JOIN actions
              ON actions.tool_name = 'create_calendar_event'
             AND actions.status = 'executed'
             AND (actions.output_json::jsonb ->> 'event_id')::BIGINT = calendar_events.id
            LEFT JOIN action_owners ON action_owners.action_id = actions.id
            WHERE calendar_events.id = %s AND {ownership_filter}
            """,
            (event_id, owner_parameter),
        ).fetchone()
        if event is None:
            raise ValueError(f"Événement introuvable : {event_id}")

        conn.execute("DELETE FROM calendar_events WHERE id = %s", (event_id,))
        conn.execute(
            "UPDATE actions SET status = 'cancelled', updated_at = NOW() WHERE id = %s",
            (event["action_id"],),
        )
        conn.execute(
            """
            UPDATE audit_log
            SET status = 'cancelled', error = %s, created_at = NOW()
            WHERE idempotency_key = %s
            """,
            ("Événement supprimé depuis le calendrier", event["idempotency_key"]),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    refresh_plan_status(event["plan_id"])
    return {
        "event_id": event_id,
        "title": event["title"],
        "action_id": event["action_id"],
        "status": "deleted",
    }
