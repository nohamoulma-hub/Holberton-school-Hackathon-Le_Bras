import json
import os
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db import get_connection


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
) -> list[dict[str, Any]]:
    """Liste les événements exécutés dans une période, avec des participants décodés."""
    if start_date and end_date and end_date <= start_date:
        raise ValueError("La date de fin doit être postérieure à la date de début")

    timezone = _application_timezone()
    filters = []
    parameters: list[datetime] = []
    if start_date:
        filters.append("start >= %s")
        parameters.append(datetime.combine(start_date, time.min, timezone))
    if end_date:
        filters.append("start < %s")
        parameters.append(datetime.combine(end_date, time.min, timezone))

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT id, title, start, duration_min, attendees_json
            FROM calendar_events
            {where_clause}
            ORDER BY start, id
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
            }
        )
    return events
