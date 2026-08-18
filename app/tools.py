import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.db import get_connection

OUTBOX_DIR = Path(__file__).resolve().parent.parent / "outbox"


class ToolError(Exception):
    """Levée quand un outil ne peut pas réaliser son effet de bord."""


def create_issue(title: str, description: str, assignee: str, due_date: str) -> dict:
    """Insère une issue dans la table `issues` (faux issue tracker)."""
    if not title or not assignee:
        raise ToolError("title et assignee sont requis pour créer une issue")

    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO issues (title, description, assignee, due_date, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (title, description, assignee, due_date, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    issue_id = cursor.lastrowid
    conn.close()
    return {"issue_id": issue_id}


def send_message(channel: str, recipient: str, content: str) -> dict:
    """Écrit un fichier .md dans /outbox/{channel}/ (faux service de messagerie)."""
    if not channel or not content:
        raise ToolError("channel et content sont requis pour envoyer un message")

    channel_dir = OUTBOX_DIR / channel
    channel_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    message_id = f"msg_{timestamp}"
    file_path = channel_dir / f"{message_id}.md"
    file_path.write_text(f"# À : {recipient}\n\n{content}\n", encoding="utf-8")
    return {"message_id": message_id, "path": str(file_path.relative_to(OUTBOX_DIR.parent))}


TOOL_IMPLEMENTATIONS: dict[str, Callable[..., dict]] = {
    "create_issue": create_issue,
    "send_message": send_message,
}


TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "create_issue",
        "description": (
            "Crée une issue dans le faux issue tracker (base SQLite) pour suivre une tâche "
            "concrète à faire par quelqu'un dans l'équipe (onboarding, bug, action de suivi...). "
            "Utilise cet outil quand la demande implique de créer, suivre ou assigner une tâche. "
            "N'utilise PAS cet outil pour simplement prévenir ou informer quelqu'un sans tâche à "
            "suivre : dans ce cas utilise send_message. Retourne l'identifiant de l'issue créée."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titre court de l'issue"},
                "description": {"type": "string", "description": "Détail de la tâche à faire"},
                "assignee": {"type": "string", "description": "Nom de la personne assignée à la tâche"},
                "due_date": {
                    "type": "string",
                    "description": "Date d'échéance au format YYYY-MM-DD",
                },
            },
            "required": ["title", "description", "assignee", "due_date"],
        },
    },
    {
        "name": "send_message",
        "description": (
            "Envoie un message à une personne ou une équipe via le faux service de messagerie "
            "(écrit un fichier .md dans /outbox/{channel}/). Utilise cet outil pour prévenir, "
            "informer ou notifier quelqu'un en langage naturel, sans créer de tâche à suivre. "
            "N'utilise PAS cet outil pour créer une tâche ou un ticket : dans ce cas utilise "
            "create_issue. Retourne l'identifiant du message envoyé."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Nom du canal ou de l'équipe destinataire, ex: 'data-team'",
                },
                "recipient": {
                    "type": "string",
                    "description": "Nom de la personne ou du groupe destinataire",
                },
                "content": {"type": "string", "description": "Contenu du message à envoyer"},
            },
            "required": ["channel", "recipient", "content"],
        },
    },
]


def _idempotency_key(tool_name: str, tool_input: dict) -> str:
    payload = json.dumps({"tool": tool_name, "input": tool_input}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_cached_result(idempotency_key: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT output_json, status FROM audit_log WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    conn.close()
    if row and row["status"] == "success" and row["output_json"]:
        return json.loads(row["output_json"])
    return None


def _log_audit(
    idempotency_key: str,
    tool_name: str,
    tool_input: dict,
    status: str,
    output: dict | None = None,
    error: str | None = None,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO audit_log
            (idempotency_key, tool_name, input_json, output_json, status, error, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            idempotency_key,
            tool_name,
            json.dumps(tool_input),
            json.dumps(output) if output is not None else None,
            status,
            error,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def execute_tool(tool_name: str, tool_input: dict) -> dict[str, Any]:
    """Exécute un outil de façon idempotente et journalise l'appel.

    Ne lève jamais d'exception : retourne toujours {"ok": bool, "result"|"error": ...},
    pour que l'agent puisse dire qu'il n'a pas pu plutôt que de planter ou d'inventer.
    """
    idempotency_key = _idempotency_key(tool_name, tool_input)

    cached = _get_cached_result(idempotency_key)
    if cached is not None:
        return {"ok": True, "result": cached, "idempotent_replay": True}

    implementation = TOOL_IMPLEMENTATIONS.get(tool_name)
    if implementation is None:
        error = f"Outil inconnu : {tool_name}"
        _log_audit(idempotency_key, tool_name, tool_input, "error", error=error)
        return {"ok": False, "error": error}

    try:
        result = implementation(**tool_input)
    except Exception as exc:
        error = str(exc)
        _log_audit(idempotency_key, tool_name, tool_input, "error", error=error)
        return {"ok": False, "error": error}

    _log_audit(idempotency_key, tool_name, tool_input, "success", output=result)
    return {"ok": True, "result": result, "idempotent_replay": False}