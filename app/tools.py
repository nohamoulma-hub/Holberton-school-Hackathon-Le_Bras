import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.db import get_connection
from app.plans import ensure_plan, refresh_plan_status

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTBOX_DIR = PROJECT_DIR / "outbox"
FILES_DIR = PROJECT_DIR / "files"

READ_ONLY_TOOLS = frozenset({"list_pending_actions"})
SIDE_EFFECT_TOOLS = frozenset(
    {
        "create_issue",
        "send_message",
        "write_record",
        "generate_document",
        "create_calendar_event",
        "undo_last_action",
    }
)
REVERSIBLE_TOOLS = frozenset(
    {
        "create_issue",
        "send_message",
        "write_record",
        "generate_document",
        "create_calendar_event",
    }
)


class ToolError(Exception):
    """Levée quand un outil ne peut pas réaliser l'action demandée."""


def _required_text(value: str, field_name: str, max_length: int = 10_000) -> str:
    """Valide un texte requis sans laisser passer une valeur vide ou démesurée."""
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"{field_name} est requis")
    cleaned = value.strip()
    if len(cleaned) > max_length:
        raise ToolError(f"{field_name} dépasse la taille maximale de {max_length} caractères")
    return cleaned


def _safe_directory_name(value: str, field_name: str) -> str:
    """Valide un nom de sous-dossier et bloque toute sortie du dossier dédié."""
    name = _required_text(value, field_name, 100)
    if name in {".", ".."} or not re.fullmatch(r"[\w.-]+", name, flags=re.UNICODE):
        raise ToolError(f"{field_name} contient des caractères non autorisés")
    return name


def _safe_markdown_path(filename: str) -> Path:
    """Construit un chemin Markdown strictement contenu dans le dossier `files`."""
    safe_name = _required_text(filename, "filename", 150)
    if Path(safe_name).name != safe_name or safe_name in {".", ".."}:
        raise ToolError("filename doit être un simple nom de fichier")
    if Path(safe_name).suffix.lower() not in {"", ".md", ".markdown"}:
        raise ToolError("generate_document accepte uniquement les fichiers Markdown")
    if not Path(safe_name).suffix:
        safe_name += ".md"
    return FILES_DIR / safe_name


def create_issue(
    title: str, description: str, assignee: str, due_date: date | str
) -> dict:
    """Insère une issue dans PostgreSQL, qui simule un issue tracker local."""
    title = _required_text(title, "title", 200)
    description = _required_text(description, "description")
    assignee = _required_text(assignee, "assignee", 200)
    if isinstance(due_date, datetime):
        raise ToolError("due_date doit être une date sans heure")
    if isinstance(due_date, date):
        parsed_due_date = due_date
    else:
        try:
            parsed_due_date = date.fromisoformat(due_date)
        except (TypeError, ValueError) as exc:
            raise ToolError("due_date doit respecter le format YYYY-MM-DD") from exc

    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO issues (title, description, assignee, due_date, created_at) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (
                title,
                description,
                assignee,
                parsed_due_date.isoformat(),
                datetime.now(timezone.utc),
            ),
        )
        issue_id = cursor.fetchone()["id"]
        conn.commit()
        return {"issue_id": issue_id}
    finally:
        conn.close()


def send_message(channel: str, recipient: str, content: str) -> dict:
    """Simule un envoi en écrivant un message Markdown dans `outbox/{channel}`."""
    channel = _safe_directory_name(channel, "channel")
    recipient = _required_text(recipient, "recipient", 200)
    content = _required_text(content, "content")

    channel_dir = OUTBOX_DIR / channel
    channel_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    message_id = f"msg_{timestamp}"
    file_path = channel_dir / f"{message_id}.md"
    file_path.write_text(f"# À : {recipient}\n\n{content}\n", encoding="utf-8")
    return {"message_id": message_id, "path": str(file_path.relative_to(PROJECT_DIR))}


def write_record(record_type: str, subject: str, payload: dict[str, Any]) -> dict:
    """Enregistre une fiche métier générique dans la table PostgreSQL `records`."""
    record_type = _required_text(record_type, "record_type", 100)
    subject = _required_text(subject, "subject", 300)
    if not isinstance(payload, dict):
        raise ToolError("payload doit être un objet JSON")
    try:
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ToolError("payload doit contenir uniquement des valeurs JSON valides") from exc
    if len(payload_json) > 20_000:
        raise ToolError("payload dépasse la taille maximale de 20 000 caractères")

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO records (record_type, subject, payload_json, created_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (record_type, subject, payload_json, datetime.now(timezone.utc)),
        )
        record_id = cursor.fetchone()["id"]
        conn.commit()
        return {"record_id": record_id}
    finally:
        conn.close()


def generate_document(title: str, content: str, filename: str) -> dict:
    """Génère un fichier Markdown dans le dossier local dédié `files`."""
    title = _required_text(title, "title", 300)
    content = _required_text(content, "content", 50_000)
    file_path = _safe_markdown_path(filename)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    if file_path.exists():
        raise ToolError(f"Le document {file_path.name} existe déjà")
    file_path.write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
    return {"path": str(file_path.relative_to(PROJECT_DIR))}


def create_calendar_event(
    title: str, start: datetime | str, duration_min: int, attendees: list[str]
) -> dict:
    """Simule un calendrier en enregistrant un événement dans PostgreSQL."""
    title = _required_text(title, "title", 300)
    if isinstance(start, datetime):
        parsed_start = start
    else:
        try:
            parsed_start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ToolError("start doit être une date et heure ISO 8601") from exc
    if not isinstance(duration_min, int) or isinstance(duration_min, bool) or duration_min <= 0:
        raise ToolError("duration_min doit être un entier strictement positif")
    if duration_min > 10_080:
        raise ToolError("duration_min ne peut pas dépasser 10 080 minutes")
    if not isinstance(attendees, list):
        raise ToolError("attendees doit être une liste")
    cleaned_attendees = [
        _required_text(attendee, "attendee", 200) for attendee in attendees
    ]

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO calendar_events
                (title, start, duration_min, attendees_json, created_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                title,
                parsed_start.isoformat(),
                duration_min,
                json.dumps(cleaned_attendees, ensure_ascii=False),
                datetime.now(timezone.utc),
            ),
        )
        event_id = cursor.fetchone()["id"]
        conn.commit()
        return {"event_id": event_id}
    finally:
        conn.close()


def list_pending_actions(plan_id: str) -> list[dict[str, Any]]:
    """Liste au plus 50 actions en attente d'un plan, sans effet de bord."""
    plan_id = _required_text(plan_id, "plan_id", 100)
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, action_index, tool_name, input_json, status, created_at
            FROM actions
            WHERE plan_id = %s AND status = 'pending'
            ORDER BY id ASC
            LIMIT 50
            """,
            (plan_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "action_id": row["id"],
            "action_index": row["action_index"],
            "tool": row["tool_name"],
            "input": json.loads(row["input_json"]),
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _remove_generated_file(relative_path: str, allowed_root: Path) -> None:
    """Supprime un fichier généré après vérification de son dossier racine."""
    file_path = (PROJECT_DIR / relative_path).resolve()
    try:
        file_path.relative_to(allowed_root.resolve())
    except ValueError as exc:
        raise ToolError("Le fichier à annuler est hors du dossier autorisé") from exc
    if not file_path.is_file():
        raise ToolError("Le fichier à annuler n'existe plus")
    file_path.unlink()


def undo_last_action(action_id: str) -> dict:
    """Annule une action exécutée et réversible, une seule fois."""
    try:
        parsed_action_id = int(action_id)
    except (TypeError, ValueError) as exc:
        raise ToolError("action_id doit être un identifiant entier") from exc

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT tool_name, output_json, status FROM actions WHERE id = %s",
            (parsed_action_id,),
        ).fetchone()
        if row is None:
            raise ToolError(f"Action introuvable : {action_id}")
        if row["status"] == "cancelled":
            raise ToolError("Cette action a déjà été annulée")
        if row["status"] != "executed":
            raise ToolError("Seule une action exécutée peut être annulée")
        if row["tool_name"] not in REVERSIBLE_TOOLS:
            raise ToolError(f"L'outil {row['tool_name']} n'est pas réversible")

        output = json.loads(row["output_json"] or "{}")
        if row["tool_name"] == "create_issue":
            cursor = conn.execute("DELETE FROM issues WHERE id = %s", (output.get("issue_id"),))
            if cursor.rowcount != 1:
                raise ToolError("L'issue à annuler n'existe plus")
        elif row["tool_name"] == "send_message":
            _remove_generated_file(output.get("path", ""), OUTBOX_DIR)
        elif row["tool_name"] == "write_record":
            cursor = conn.execute("DELETE FROM records WHERE id = %s", (output.get("record_id"),))
            if cursor.rowcount != 1:
                raise ToolError("Le record à annuler n'existe plus")
        elif row["tool_name"] == "generate_document":
            _remove_generated_file(output.get("path", ""), FILES_DIR)
        elif row["tool_name"] == "create_calendar_event":
            cursor = conn.execute(
                "DELETE FROM calendar_events WHERE id = %s", (output.get("event_id"),)
            )
            if cursor.rowcount != 1:
                raise ToolError("L'événement à annuler n'existe plus")

        now = datetime.now(timezone.utc)
        conn.execute(
            "UPDATE actions SET status = 'cancelled', updated_at = %s WHERE id = %s",
            (now, parsed_action_id),
        )
        conn.commit()
        return {"undone": True, "action_id": parsed_action_id, "tool": row["tool_name"]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


TOOL_IMPLEMENTATIONS: dict[str, Callable[..., Any]] = {
    "create_issue": create_issue,
    "send_message": send_message,
    "write_record": write_record,
    "generate_document": generate_document,
    "create_calendar_event": create_calendar_event,
    "list_pending_actions": list_pending_actions,
    "undo_last_action": undo_last_action,
}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "create_issue",
        "description": (
            "Propose la création d'une tâche dans le faux issue tracker SQLite. À utiliser pour "
            "créer, suivre ou assigner une tâche concrète. Effet de bord : nécessite une "
            "validation humaine avant exécution. Retourne un identifiant d'issue après validation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titre court de l'issue"},
                "description": {"type": "string", "description": "Détail de la tâche"},
                "assignee": {"type": "string", "description": "Personne assignée"},
                "due_date": {
                    "type": "string",
                    "format": "date",
                    "description": "Échéance au format YYYY-MM-DD",
                },
            },
            "required": ["title", "description", "assignee", "due_date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "send_message",
        "description": (
            "Propose l'envoi simulé d'un message professionnel, enregistré en Markdown dans "
            "outbox/{channel}. À utiliser pour informer ou notifier, pas pour créer une tâche. "
            "Effet de bord : nécessite une validation humaine avant exécution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Canal destinataire"},
                "recipient": {"type": "string", "description": "Personne ou groupe destinataire"},
                "content": {"type": "string", "description": "Contenu professionnel du message"},
            },
            "required": ["channel", "recipient", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_record",
        "description": (
            "Propose l'enregistrement d'une information métier générique dans SQLite, par exemple "
            "une fiche d'onboarding, un incident ou un événement. Effet de bord : nécessite une "
            "validation humaine avant exécution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "record_type": {"type": "string", "description": "Type générique de la fiche"},
                "subject": {"type": "string", "description": "Sujet principal de la fiche"},
                "payload": {
                    "type": "object",
                    "description": "Données structurées à enregistrer",
                },
            },
            "required": ["record_type", "subject", "payload"],
            "additionalProperties": False,
        },
    },
    {
        "name": "generate_document",
        "description": (
            "Propose la génération locale d'un document texte au format Markdown dans le dossier "
            "files. Aucun PDF ou DOCX n'est produit. Effet de bord : nécessite une validation "
            "humaine avant exécution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titre du document"},
                "content": {"type": "string", "description": "Contenu du document"},
                "filename": {"type": "string", "description": "Nom simple terminé par .md"},
            },
            "required": ["title", "content", "filename"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_calendar_event",
        "description": (
            "Propose la création simulée d'un événement de calendrier enregistré dans SQLite. "
            "Effet de bord : nécessite une validation humaine avant exécution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titre de l'événement"},
                "start": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Début au format ISO 8601",
                },
                "duration_min": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Durée en minutes",
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste des participants",
                },
            },
            "required": ["title", "start", "duration_min", "attendees"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_pending_actions",
        "description": (
            "Liste les actions d'un plan qui attendent encore une validation humaine. Cet outil "
            "est en lecture seule et peut être exécuté immédiatement."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "Identifiant du plan à consulter"}
            },
            "required": ["plan_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "undo_last_action",
        "description": (
            "Propose l'annulation d'une action locale déjà exécutée et réversible. Ne fonctionne "
            "pas sur une action en attente, refusée, inconnue ou déjà annulée. Effet de bord : "
            "nécessite une validation humaine avant exécution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action_id": {
                    "type": "string",
                    "description": "Identifiant de l'action exécutée à annuler",
                }
            },
            "required": ["action_id"],
            "additionalProperties": False,
        },
    },
]


_TOOL_NAMES: frozenset[str] = frozenset(tool["name"] for tool in TOOL_DEFINITIONS)

# État en mémoire des outils désactivés (démo palier 3 : "je débranche un outil"), piloté
# depuis le front sans redémarrer le serveur. Réinitialisé au démarrage à partir de
# DISABLED_TOOLS dans .env, pour partir avec un état connu.
_disabled_tools: set[str] = {
    name.strip() for name in os.environ.get("DISABLED_TOOLS", "").split(",") if name.strip()
} & set(_TOOL_NAMES)


def list_tool_status() -> list[dict[str, Any]]:
    """Liste chaque outil connu avec son état actif/inactif, pour le panneau du front."""
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "enabled": tool["name"] not in _disabled_tools,
        }
        for tool in TOOL_DEFINITIONS
    ]


def set_tool_enabled(tool_name: str, enabled: bool) -> dict[str, Any]:
    """Active ou désactive un outil pour les prochains appels de l'agent."""
    if tool_name not in _TOOL_NAMES:
        raise ToolError(f"Outil inconnu : {tool_name}")
    if enabled:
        _disabled_tools.discard(tool_name)
    else:
        _disabled_tools.add(tool_name)
    return {"name": tool_name, "enabled": enabled}


def get_active_tool_definitions() -> list[dict[str, Any]]:
    """Sous-ensemble de TOOL_DEFINITIONS effectivement proposé à Claude en ce moment."""
    return [tool for tool in TOOL_DEFINITIONS if tool["name"] not in _disabled_tools]


def _idempotency_key(
    plan_id: str,
    action_index: int,
    tool_name: str,
    tool_input: dict[str, Any],
) -> str:
    payload = json.dumps(
        {
            "plan_id": plan_id,
            "action_index": action_index,
            "tool": tool_name,
            "input": tool_input,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_cached_result(idempotency_key: str) -> tuple[Any, int] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, output_json, status FROM audit_log WHERE idempotency_key = %s",
            (idempotency_key,),
        ).fetchone()
    finally:
        conn.close()
    if row and row["status"] == "success" and row["output_json"]:
        return json.loads(row["output_json"]), row["id"]
    return None


def _log_audit(
    idempotency_key: str,
    tool_name: str,
    tool_input: dict[str, Any],
    status: str,
    output: Any = None,
    error: str | None = None,
) -> int:
    """Crée ou actualise la trace d'une même action sans changer son identifiant."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO audit_log
                (idempotency_key, tool_name, input_json, output_json, status, error, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(idempotency_key) DO UPDATE SET
                tool_name = EXCLUDED.tool_name,
                input_json = EXCLUDED.input_json,
                output_json = EXCLUDED.output_json,
                status = EXCLUDED.status,
                error = EXCLUDED.error,
                created_at = EXCLUDED.created_at
            """,
            (
                idempotency_key,
                tool_name,
                json.dumps(tool_input, ensure_ascii=False, default=str),
                json.dumps(output, ensure_ascii=False) if output is not None else None,
                status,
                error,
                datetime.now(timezone.utc),
            ),
        )
        audit_id = conn.execute(
            "SELECT id FROM audit_log WHERE idempotency_key = %s", (idempotency_key,)
        ).fetchone()["id"]
        conn.commit()
        return audit_id
    finally:
        conn.close()


def _queue_pending_action(
    plan_id: str,
    action_index: int,
    tool_name: str,
    tool_input: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    """Enregistre une proposition d'effet de bord sans l'exécuter."""
    ensure_plan(plan_id)
    now = datetime.now(timezone.utc)
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO actions
                (plan_id, action_index, tool_name, input_json, status, idempotency_key,
                 created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                plan_id,
                action_index,
                tool_name,
                json.dumps(tool_input, ensure_ascii=False, default=str),
                idempotency_key,
                now,
                now,
            ),
        )
        inserted = cursor.fetchone()
        row = conn.execute(
            """
            SELECT id, plan_id, action_index, status, output_json, error
            FROM actions
            WHERE idempotency_key = %s
            """,
            (idempotency_key,),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    result: dict[str, Any] = {
        "action_id": row["id"],
        "plan_id": row["plan_id"],
        "action_index": row["action_index"],
        "status": row["status"],
        "_created": inserted is not None,
    }
    if row["output_json"]:
        result["result"] = json.loads(row["output_json"])
    if row["error"]:
        result["error"] = row["error"]
    return result


def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    plan_id: str = "default",
    action_index: int = 0,
    approved: bool = False,
) -> dict[str, Any]:
    """Exécute un outil en lecture seule ou prépare un effet de bord à valider.

    Une action avec effet de bord n'est exécutée que si `approved=True`, valeur réservée
    au backend après validation humaine. Toute issue est journalisée et aucune exception
    n'est propagée vers la boucle de l'agent.
    """
    implementation = TOOL_IMPLEMENTATIONS.get(tool_name)
    idempotency_key = _idempotency_key(plan_id, action_index, tool_name, tool_input)

    if implementation is None:
        error = f"Outil inconnu : {tool_name}"
        audit_id = _log_audit(idempotency_key, tool_name, tool_input, "error", error=error)
        return {"ok": False, "error": error, "status": "error", "audit_id": audit_id}

    if tool_name in SIDE_EFFECT_TOOLS and not approved:
        pending = _queue_pending_action(
            plan_id, action_index, tool_name, tool_input, idempotency_key
        )
        was_created = pending.pop("_created")
        if pending["status"] == "executed":
            cached = _get_cached_result(idempotency_key)
            if cached is not None:
                cached_result, audit_id = cached
                return {
                    "ok": True,
                    "result": cached_result,
                    "status": "success",
                    "audit_id": audit_id,
                    "idempotent_replay": True,
                }
        if pending["status"] != "pending":
            return {
                "ok": False,
                "error": f"L'action identique est déjà {pending['status']}",
                "status": pending["status"],
                "idempotent_replay": True,
            }
        audit_id = _log_audit(
            idempotency_key, tool_name, tool_input, pending["status"], output=pending
        )
        return {
            "ok": True,
            "result": pending,
            "status": pending["status"],
            "audit_id": audit_id,
            "idempotent_replay": not was_created,
        }

    if tool_name not in READ_ONLY_TOOLS:
        cached = _get_cached_result(idempotency_key)
        if cached is not None:
            cached_result, audit_id = cached
            return {
                "ok": True,
                "result": cached_result,
                "status": "success",
                "audit_id": audit_id,
                "idempotent_replay": True,
            }

    try:
        result = implementation(**tool_input)
    except Exception as exc:
        error = str(exc)
        audit_id = _log_audit(idempotency_key, tool_name, tool_input, "error", error=error)
        return {"ok": False, "error": error, "status": "error", "audit_id": audit_id}

    audit_id = _log_audit(idempotency_key, tool_name, tool_input, "success", output=result)
    return {
        "ok": True,
        "result": result,
        "status": "success",
        "audit_id": audit_id,
        "idempotent_replay": False,
    }


def approve_pending_action(action_id: int) -> dict[str, Any]:
    """Vérifie puis exécute une action explicitement approuvée par l'utilisateur."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            UPDATE actions
            SET status = 'executing', updated_at = %s
            WHERE id = %s AND status = 'pending'
            RETURNING *
            """,
            (datetime.now(timezone.utc), action_id),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM actions WHERE id = %s",
                (action_id,),
            ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if row is None:
        return {"ok": False, "error": f"Action introuvable : {action_id}"}
    if row["status"] == "executed":
        return {
            "ok": True,
            "status": "executed",
            "result": json.loads(row["output_json"] or "{}"),
            "idempotent_replay": True,
        }
    if row["status"] != "executing":
        return {"ok": False, "error": f"L'action est déjà {row['status']}"}

    tool_input = json.loads(row["input_json"])
    result = execute_tool(
        row["tool_name"],
        tool_input,
        plan_id=row["plan_id"],
        action_index=row["action_index"],
        approved=True,
    )
    now = datetime.now(timezone.utc)
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE actions
            SET status = %s, output_json = %s, error = %s, updated_at = %s
            WHERE id = %s AND status = 'executing'
            """,
            (
                "executed" if result["ok"] else "error",
                json.dumps(result.get("result"), ensure_ascii=False)
                if result.get("result") is not None
                else None,
                result.get("error"),
                now,
                action_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    refresh_plan_status(row["plan_id"])
    return {**result, "action_id": action_id, "status": "executed" if result["ok"] else "error"}


def reject_pending_action(action_id: int) -> dict[str, Any]:
    """Refuse une action en attente sans jamais appeler son implémentation."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM actions WHERE id = %s", (action_id,)).fetchone()
        if row is None:
            return {"ok": False, "error": f"Action introuvable : {action_id}"}
        if row["status"] != "pending":
            return {"ok": False, "error": f"L'action est déjà {row['status']}"}
        now = datetime.now(timezone.utc)
        conn.execute(
            "UPDATE actions SET status = 'rejected', updated_at = %s WHERE id = %s",
            (now, action_id),
        )
        conn.commit()
    finally:
        conn.close()

    tool_input = json.loads(row["input_json"])
    _log_audit(
        row["idempotency_key"], row["tool_name"], tool_input, "rejected", error="Action refusée"
    )
    refresh_plan_status(row["plan_id"])
    return {"ok": True, "action_id": action_id, "status": "rejected"}
