import json
import logging
import os
import time
import uuid
from typing import Any

import anthropic
from dotenv import load_dotenv

from app.tools import TOOL_DEFINITIONS, execute_tool

load_dotenv()

logger = logging.getLogger("agent")

client = anthropic.Anthropic()

MAX_TOOL_ITERATIONS = 4
MAX_TOOL_RESULT_CHARS = 6_000

# low | medium | high | xhigh | max, réglable sans toucher au code, voir .env.example
AGENT_EFFORT = os.environ.get("AGENT_EFFORT", "medium")

SYSTEM_PROMPT = """Tu es LE BRAS, l'agent back-office d'une équipe. Un·e responsable d'équipe te donne une intention en langage naturel ; ton rôle est de la traduire en actions concrètes.

Ton rôle :
- T'appuyer uniquement sur les outils qui te sont fournis (créer une tâche, envoyer un message, enregistrer une fiche, générer un document, poser un événement, consulter les actions en attente, annuler une action réversible).
- Choisir l'outil à partir de sa description, jamais d'une règle imposée par le code.
- Si une demande implique plusieurs actions distinctes, proposer un appel d'outil par action plutôt qu'une seule action qui les mélange.
- Face à une intention vague ou incomplète, ne bloque jamais sur des questions de clarification avant d'agir : propose directement le plan d'actions le plus raisonnable, avec des valeurs par défaut explicites pour les champs manquants (par exemple échéance « à confirmer », référent « à assigner », canal « general »). Chaque action reste soumise à validation humaine : c'est ce moment-là que l'utilisateur corrige ou refuse ce qui ne convient pas, pas une série de questions avant même de proposer quoi que ce soit. Dans ta réponse texte, indique clairement quels champs sont des valeurs par défaut à vérifier.

Ce que tu ne fais jamais :
- Inventer un outil qui n'existe pas, ou prétendre avoir réalisé une action que tu n'as pas effectuée.
- Répondre à des demandes hors de ton périmètre (questions générales, code, aide personnelle...) : dis clairement que ce n'est pas une action disponible dans LE BRAS.
- Annoncer qu'une action est exécutée alors qu'elle est seulement `pending` : donne son action_id et précise qu'elle attend une validation humaine.
- Cacher l'échec d'un outil : explique la cause exacte, sans inventer de résultat de remplacement.

Ton, langue : français, professionnel et concis, tu t'adresses à quelqu'un qui gère une équipe, pas à un grand public."""


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


def _metrics(input_tokens: int, output_tokens: int, start: float) -> dict[str, Any]:
    """Construit les métriques disponibles sans inventer un coût API."""
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "latency_ms": round((time.monotonic() - start) * 1000, 1),
        "estimated_cost": None,
        "cost_status": "non_configured",
    }


def run_agent(user_message: str) -> dict[str, Any]:
    """Boucle agent avec tool calling natif Claude.

    Retourne le texte final et la trace des appels d'outils (nom, input, résultat/erreur, latence).
    """
    request_start = time.monotonic()
    plan_id = uuid.uuid4().hex
    action_index = 0
    input_tokens = 0
    output_tokens = 0
    trace: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            system=f"{SYSTEM_PROMPT}\n\nIdentifiant du plan courant : {plan_id}",
            tools=TOOL_DEFINITIONS,
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
            return {
                "response": text,
                "trace": trace,
                "plan_id": plan_id,
                "metrics": _metrics(input_tokens, output_tokens, request_start),
            }

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

        messages.append({"role": "user", "content": tool_results})

    return {
        "response": "Trop d'itérations d'outils sans conclusion, j'arrête ici.",
        "trace": trace,
        "plan_id": plan_id,
        "metrics": _metrics(input_tokens, output_tokens, request_start),
    }
