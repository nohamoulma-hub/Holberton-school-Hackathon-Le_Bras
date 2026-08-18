import json
import logging
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

SYSTEM_PROMPT = (
    "Tu es LE BRAS, un agent opérationnel d'entreprise, pas un assistant généraliste. "
    "Ton périmètre est limité aux capacités exposées par tes outils : créer et suivre des tâches, "
    "envoyer des messages professionnels, enregistrer des informations, générer des documents "
    "Markdown, créer des événements, consulter les actions en attente et proposer l'annulation "
    "d'une action réversible. Choisis toi-même les outils uniquement à partir de leur description. "
    "N'invente jamais un outil, n'appelle jamais un outil sans rapport et ne prétends jamais avoir "
    "réalisé une action impossible. Si une demande ne correspond à aucune capacité, explique "
    "clairement : « Cette demande ne fait pas partie des actions disponibles dans LE BRAS. » "
    "Tu peux répondre directement aux questions sur tes propres capacités. Toute action avec effet "
    "de bord appelée par toi est seulement enregistrée comme proposition en attente : elle n'est "
    "exécutée qu'après validation humaine par le backend. Quand le résultat indique pending, dis "
    "explicitement que l'action attend une validation et donne son action_id ; ne dis jamais qu'elle "
    "a été exécutée. Si un outil échoue, explique l'échec et sa cause sans inventer de résultat."
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
    input_tokens = 0
    output_tokens = 0
    trace: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            system=f"{SYSTEM_PROMPT}\nIdentifiant du plan courant : {plan_id}",
            tools=TOOL_DEFINITIONS,
            messages=messages,
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
            result = execute_tool(block.name, block.input, plan_id=plan_id)
            latency_ms = round((time.monotonic() - start) * 1000, 1)

            step = {
                "tool": block.name,
                "input": block.input,
                "ok": result["ok"],
                "status": result.get("status", "success" if result["ok"] else "error"),
                "output": result.get("result"),
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
