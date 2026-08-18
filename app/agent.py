import logging
import time
from typing import Any

import anthropic
from dotenv import load_dotenv

from app.tools import TOOL_DEFINITIONS, execute_tool

load_dotenv()

logger = logging.getLogger("agent")

client = anthropic.Anthropic()

MAX_TOOL_ITERATIONS = 4

SYSTEM_PROMPT = (
    "Tu es l'agent back du projet Le Bras. Tu as accès à des outils à effets de bord réels "
    "(création d'issue, envoi de message...). Choisis l'outil adapté à la demande de l'utilisateur "
    "en te basant sur sa description, sans règle fixe imposée par le code. Si un outil échoue ou "
    "renvoie une erreur, explique clairement à l'utilisateur que l'action n'a pas pu être réalisée "
    "et pourquoi, plutôt que d'inventer un résultat. Si aucun outil n'est nécessaire, réponds "
    "directement sans en appeler un."
)


def run_agent(user_message: str) -> dict[str, Any]:
    """Boucle agent avec tool calling natif Claude.

    Retourne le texte final et la trace des appels d'outils (nom, input, résultat/erreur, latence).
    """
    trace: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
        if not tool_use_blocks:
            text = next((block.text for block in response.content if block.type == "text"), "")
            return {"response": text, "trace": trace}

        tool_results = []
        for block in tool_use_blocks:
            start = time.monotonic()
            result = execute_tool(block.name, block.input)
            latency_ms = round((time.monotonic() - start) * 1000, 1)

            step = {
                "tool": block.name,
                "input": block.input,
                "ok": result["ok"],
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
                    "content": str(
                        result.get("result") if result["ok"] else f"ERREUR: {result['error']}"
                    ),
                    "is_error": not result["ok"],
                }
            )

        messages.append({"role": "user", "content": tool_results})

    return {
        "response": "Trop d'itérations d'outils sans conclusion, j'arrête ici.",
        "trace": trace,
    }