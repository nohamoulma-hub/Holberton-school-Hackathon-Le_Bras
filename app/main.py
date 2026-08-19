import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent import run_agent
from app.accounts import (
    AccountError,
    SESSION_COOKIE_NAME,
    SESSION_DURATION_DAYS,
    authenticate_user,
    create_session,
    create_user,
    delete_session,
    get_user_from_session,
)
from app.db import get_recent_audit_log, init_db
from app.history import (
    link_actions_to_user,
    list_accepted_actions,
    list_conversations,
    save_conversation,
)
from app.tools import (
    ToolError,
    approve_pending_action,
    list_tool_status,
    reject_pending_action,
    set_tool_enabled,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("main")

init_db()

app = FastAPI(title="Le Bras - Back")


class ChatRequest(BaseModel):
    message: str


class ToolToggleRequest(BaseModel):
    enabled: bool


class AccountRequest(BaseModel):
    email: str
    password: str


def current_user(request: Request, required: bool = True) -> dict | None:
    user = get_user_from_session(request.cookies.get(SESSION_COOKIE_NAME))
    if required and user is None:
        raise HTTPException(status_code=401, detail="Connexion requise")
    return user


def set_session_cookie(response: Response, token: str) -> None:
    secure_cookie = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_DURATION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat")
def chat(body: ChatRequest, request: Request) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY manquante (voir .env)")

    result = run_agent(body.message)
    user = current_user(request, required=False)
    if user is not None:
        try:
            result["conversation_id"] = save_conversation(user["id"], body.message, result)
            link_actions_to_user(user["id"], result.get("trace", []))
        except Exception:
            logger.exception("Impossible d'enregistrer l'historique de la conversation")
    return result


@app.post("/auth/register")
def register(body: AccountRequest, response: Response) -> dict:
    try:
        user = create_user(body.email, body.password)
    except AccountError as exc:
        status_code = 409 if "existe déjà" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    set_session_cookie(response, create_session(user["id"]))
    return {"user": user}


@app.post("/auth/login")
def login(body: AccountRequest, response: Response) -> dict:
    try:
        user = authenticate_user(body.email, body.password)
    except AccountError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    set_session_cookie(response, create_session(user["id"]))
    return {"user": user}


@app.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    delete_session(request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"status": "disconnected"}


@app.get("/auth/me")
def me(request: Request) -> dict:
    return {"user": current_user(request)}


@app.get("/history/conversations")
def conversation_history(request: Request, limit: int = 50) -> dict:
    user = current_user(request)
    return {"conversations": list_conversations(user["id"], limit)}


@app.get("/history/accepted-actions")
def accepted_action_history(request: Request, limit: int = 50) -> dict:
    user = current_user(request)
    return {"actions": list_accepted_actions(user["id"], limit)}


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
