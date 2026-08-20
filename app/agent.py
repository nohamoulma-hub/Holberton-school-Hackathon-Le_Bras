import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()

import anthropic

from app.plans import create_plan, finalize_plan
from app.tools import execute_tool, get_active_tool_definitions

logger = logging.getLogger("agent")

client = anthropic.Anthropic()

MAX_TOOL_ITERATIONS = 4
MAX_TOOL_RESULT_CHARS = 6_000

# Les cinq catégories de création du Palier 4 doivent être réexaminées avant la
# conclusion. Cette liste décrit les capacités du produit, pas un scénario métier.
CREATION_TOOL_CATEGORIES = {
    "create_issue": "tâche",
    "send_message": "communication",
    "write_record": "fiche structurée",
    "generate_document": "document utile",
    "create_calendar_event": "événement calendrier",
}

# Tarif claude-sonnet-5 (USD par million de tokens), pour le coût affiché à l'écran.
# À ajuster si le modèle change (variable `model` de messages.create ci-dessous).
INPUT_PRICE_PER_MILLION_USD = 3.0
OUTPUT_PRICE_PER_MILLION_USD = 15.0

# low | medium | high | xhigh | max, réglable sans toucher au code, voir .env.example
AGENT_EFFORT = os.environ.get("AGENT_EFFORT", "medium")
DEFAULT_TIMEZONE = "Europe/Paris"

SYSTEM_PROMPT = """Tu es LE BRAS, l'agent back-office d'une équipe. Un·e responsable d'équipe te donne une intention en langage naturel ; ton rôle est de la traduire en actions concrètes.

Ton rôle :
- T'appuyer uniquement sur les outils qui te sont fournis (créer une tâche, envoyer un message, enregistrer une fiche, générer un document, poser un événement, consulter les actions en attente, annuler une action réversible).
- Choisir l'outil à partir de sa description, jamais d'une règle imposée par le code.
- Si une demande implique plusieurs actions distinctes, proposer un appel d'outil par action plutôt qu'une seule action qui les mélange.
- Distinguer deux types de demandes avant d'agir :
  - **Demande précise** : elle nomme déjà une action concrète et ses paramètres (par exemple « crée une tâche pour X, assignée à Y, pour telle date »). Dans ce cas, ne propose que cette action-là. N'ajoute pas de message, de fiche, de document ou d'événement que l'utilisateur n'a pas demandés, même si tu penses qu'ils pourraient être utiles dans le contexte.
  - **Demande vague ou large** : elle exprime une intention générale sans préciser quelle action concrète y répondre (par exemple « prépare l'arrivée de X », « occupe-toi de Y »). Dans ce cas seulement, propose directement le plan d'actions le plus raisonnable couvrant cette intention, avec des valeurs par défaut explicites pour les champs manquants (par exemple échéance « à confirmer », référent « à assigner », canal « general »). Ne bloque jamais sur des questions de clarification avant d'agir.
  - Dans les deux cas, chaque action reste soumise à validation humaine : c'est ce moment-là que l'utilisateur corrige ou refuse ce qui ne convient pas, pas une série de questions avant même de proposer quoi que ce soit. Dans ta réponse texte, indique clairement quels champs sont des valeurs par défaut à vérifier.
- Remplis toujours tous les champs requis d'un outil, y compris le contenu rédigé d'un document ou d'un message : rédige un brouillon plausible plutôt que de laisser un champ vide, pour qu'une action approuvée telle quelle soit exécutable. Signale ce brouillon comme provisoire dans ta réponse texte, exactement comme les autres valeurs par défaut, mais signale-le.

Ce que tu ne fais jamais :
- Inventer un outil qui n'existe pas, ou prétendre avoir réalisé une action que tu n'as pas effectuée.
- Répondre à des demandes hors de ton périmètre (questions générales, code, aide personnelle...) : dis clairement que ce n'est pas une action disponible dans LE BRAS.
- Annoncer qu'une action est exécutée alors qu'elle est seulement `pending` : donne son action_id et précise qu'elle attend une validation humaine.
- Cacher l'échec d'un outil : explique la cause exacte, sans inventer de résultat de remplacement.
- Si l'outil normalement adapté à une demande n'est pas dans la liste des outils qui te sont fournis pour cet appel, ne cherche jamais un autre outil comme contournement pour arriver quand même à un résultat proche. Dis explicitement que cette action précise n'est pas disponible pour le moment, sans rien proposer ni exécuter à la place.

Ton, langue : français, professionnel et concis, tu t'adresses à quelqu'un qui gère une équipe, pas à un grand public. N'utilise jamais le tiret cadratin « — » : préfère la virgule, le point, ou une phrase séparée."""


def get_current_datetime() -> datetime:
    """Retourne l'heure serveur dans le fuseau configuré au moment de la requête."""
    timezone_name = os.environ.get("APP_TIMEZONE", DEFAULT_TIMEZONE)
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Fuseau horaire APP_TIMEZONE invalide : {timezone_name}") from exc
    return datetime.now(timezone)


def _temporal_context() -> str:
    """Construit le contexte temporel ajouté au prompt sans modifier le prompt métier."""
    current_datetime = get_current_datetime()
    timezone_name = getattr(
        current_datetime.tzinfo,
        "key",
        os.environ.get("APP_TIMEZONE", DEFAULT_TIMEZONE),
    )
    return (
        "Contexte temporel actuel :\n"
        f"- date actuelle : {current_datetime.date().isoformat()}\n"
        f"- heure actuelle : {current_datetime.strftime('%H:%M:%S')}\n"
        f"- fuseau horaire : {timezone_name}\n\n"
        'Interprète toutes les expressions relatives comme "aujourd\'hui", "demain", '
        '"dans N jours", "lundi" et "lundi prochain" par rapport à cette date.'
    )


def _serialize_tool_result(result: dict[str, Any]) -> str:
    """Sérialise un résultat pour Claude en conservant toujours un JSON valide."""
    serialized = json.dumps(result, ensure_ascii=False, default=str)
    if len(serialized) <= MAX_TOOL_RESULT_CHARS:
        return serialized
    summary = {
        "truncated": True,
        "original_size": len(serialized),
        "preview": serialized[: MAX_TOOL_RESULT_CHARS - 200],
    }
    return json.dumps(summary, ensure_ascii=False)


def _completion_check(
    active_tools: list[dict[str, Any]], trace: list[dict[str, Any]]
) -> str | None:
    """Construit le rappel générique des catégories de création non utilisées."""
    active_names = {tool["name"] for tool in active_tools}
    used_names = {step["tool"] for step in trace}
    remaining = [
        (tool_name, category)
        for tool_name, category in CREATION_TOOL_CATEGORIES.items()
        if tool_name in active_names and tool_name not in used_names
    ]
    if not remaining:
        return None

    remaining_text = ", ".join(
        f"{category} (`{tool_name}`)" for tool_name, category in remaining
    )
    return (
        "Contrôle de complétude avant de conclure : les catégories de création "
        f"suivantes n'ont pas encore été utilisées : {remaining_text}. "
        "Réexamine chacune d'elles par rapport à l'intention complète de "
        "l'utilisateur. Appelle maintenant chaque outil encore pertinent, notamment "
        "si son résultat constitue un livrable distinct des actions déjà proposées. "
        "N'ajoute toutefois aucune action sans rapport avec la demande."
    )


def _metrics(input_tokens: int, output_tokens: int, start: float) -> dict[str, Any]:
    """Construit les métriques, avec un coût estimé sur le tarif connu de claude-sonnet-5."""
    estimated_cost = round(
        (input_tokens / 1_000_000) * INPUT_PRICE_PER_MILLION_USD
        + (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_MILLION_USD,
        6,
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "latency_ms": round((time.monotonic() - start) * 1000, 1),
        "estimated_cost": estimated_cost,
        "cost_status": "estimated",
    }


def run_agent(user_message: str) -> dict[str, Any]:
    """Boucle agent avec tool calling natif Claude.

    Retourne le texte final et la trace des appels d'outils (nom, input, résultat/erreur, latence).
    """
    request_start = time.monotonic()
    plan_id = uuid.uuid4().hex
    temporal_context = _temporal_context()
    create_plan(plan_id, user_message)
    action_index = 0
    input_tokens = 0
    output_tokens = 0
    trace: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    active_tools = get_active_tool_definitions()

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=4096,
            system=(
                f"{SYSTEM_PROMPT}\n\n{temporal_context}\n\n"
                f"Identifiant du plan courant : {plan_id}"
            ),
            tools=active_tools,
            messages=messages,
            output_config={"effort": AGENT_EFFORT},
        )
        usage = getattr(response, "usage", None)
        input_tokens += getattr(usage, "input_tokens", 0) or 0
        output_tokens += getattr(usage, "output_tokens", 0) or 0

        messages.append({"role": "assistant", "content": response.content})

        tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
        if not tool_use_blocks:
            text = next((block.text for block in response.content if block.type == "text"), "")
            metrics = _metrics(input_tokens, output_tokens, request_start)
            result = {
                "response": text,
                "trace": trace,
                "plan_id": plan_id,
                "metrics": metrics,
            }
            finalize_plan(plan_id, text, metrics)
            return result

        tool_results = []
        for block in tool_use_blocks:
            start = time.monotonic()
            current_action_index = action_index
            action_index += 1
            result = execute_tool(
                block.name,
                block.input,
                plan_id=plan_id,
                action_index=current_action_index,
            )
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            output = result.get("result")

            step = {
                "tool": block.name,
                "input": block.input,
                "action_index": current_action_index,
                "action_id": output.get("action_id") if isinstance(output, dict) else None,
                "ok": result["ok"],
                "status": result.get("status", "success" if result["ok"] else "error"),
                "output": output,
                "error": result.get("error"),
                "latency_ms": latency_ms,
            }
            trace.append(step)
            logger.info("tool_call %s", step)

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _serialize_tool_result(result),
                    "is_error": not result["ok"],
                }
            )

        completion_check = _completion_check(active_tools, trace)
        if completion_check:
            tool_results.append({"type": "text", "text": completion_check})
        messages.append({"role": "user", "content": tool_results})

    text = "Trop d'itérations d'outils sans conclusion, j'arrête ici."
    metrics = _metrics(input_tokens, output_tokens, request_start)
    result = {
        "response": text,
        "trace": trace,
        "plan_id": plan_id,
        "metrics": metrics,
    }
    finalize_plan(plan_id, text, metrics)
    return result
