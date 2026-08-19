import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent import run_agent
from app.db import get_recent_audit_log, init_db
from app.tools import (
    ToolError,
    approve_pending_action,
    list_tool_status,
    reject_pending_action,
    set_tool_enabled,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

init_db()

app = FastAPI(title="Le Bras - Back")


class ChatRequest(BaseModel):
    message: str


class ToolToggleRequest(BaseModel):
    enabled: bool


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat")
def chat(body: ChatRequest) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY manquante (voir .env)")

    return run_agent(body.message)


@app.get("/trace")
def trace(limit: int = 20) -> dict:
    """Journal des derniers appels d'outils (idempotency_key, input, résultat/erreur), pour
    montrer la séquence sans avoir besoin d'un print live."""
    return {"calls": get_recent_audit_log(limit)}


@app.get("/tools")
def tools() -> dict:
    """État actif/inactif de chaque outil, pour le panneau de contrôle du front."""
    return {"tools": list_tool_status()}


@app.post("/tools/{tool_name}/toggle")
def toggle_tool(tool_name: str, body: ToolToggleRequest) -> dict:
    """Active ou désactive un outil pour la démo (« je débranche un outil ») : effectif dès la
    prochaine requête à l'agent, sans redémarrer le serveur."""
    try:
        return set_tool_enabled(tool_name, body.enabled)
    except ToolError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/actions/{action_id}/approve")
def approve_action(action_id: int) -> dict:
    """Exécute une action uniquement après cette validation humaine explicite."""
    result = approve_pending_action(action_id)
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


@app.post("/actions/{action_id}/reject")
def reject_action(action_id: int) -> dict:
    """Refuse une action en attente sans provoquer son effet de bord."""
    result = reject_pending_action(action_id)
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
