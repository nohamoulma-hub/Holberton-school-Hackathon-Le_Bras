import logging
import os
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response
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
from app.calendar_events import delete_calendar_event, list_calendar_events
from app.db import database_is_ready, get_connection, get_recent_audit_log, init_db
from app.history import (
    hide_accepted_action,
    link_actions_to_user,
    list_accepted_actions,
    list_conversations,
    save_conversation,
)
from app.plans import assign_plan_to_user, get_latest_user_plan, get_plan
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


def verify_action_access(action_id: int, user_id: int | None) -> None:
    """Autorise les actions anonymes ou celles du compte propriétaire du plan."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT plans.user_id
            FROM actions
            JOIN plans ON plans.id = actions.plan_id
            WHERE actions.id = %s
            """,
            (action_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None or (row["user_id"] is not None and row["user_id"] != user_id):
        raise HTTPException(status_code=404, detail="Action introuvable")


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
    if not database_is_ready():
        raise HTTPException(status_code=503, detail="PostgreSQL indisponible")
    return {"status": "ok", "database": "ok"}


@app.post("/chat")
def chat(body: ChatRequest, request: Request) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("Configuration Anthropic absente")
        raise HTTPException(
            status_code=503,
            detail="Le service IA est indisponible en raison d'un problème de configuration.",
        )

    try:
        result = run_agent(body.message)
    except anthropic.AuthenticationError as exc:
        logger.exception("Échec d'authentification auprès d'Anthropic")
        raise HTTPException(
            status_code=503,
            detail="Le service IA est indisponible en raison d'un problème de configuration.",
        ) from exc
    except anthropic.APITimeoutError as exc:
        logger.exception("Délai d'attente Anthropic dépassé")
        raise HTTPException(
            status_code=504,
            detail="Le service IA met trop de temps à répondre. Veuillez réessayer.",
        ) from exc
    except anthropic.RateLimitError as exc:
        logger.exception("Limite de requêtes Anthropic atteinte")
        raise HTTPException(
            status_code=429,
            detail=(
                "Le service IA est temporairement surchargé. "
                "Veuillez réessayer dans quelques instants."
            ),
        ) from exc
    except anthropic.APIConnectionError as exc:
        logger.exception("Connexion à Anthropic impossible")
        raise HTTPException(
            status_code=503,
            detail=(
                "Impossible de contacter le service IA. "
                "Vérifiez votre connexion et réessayez."
            ),
        ) from exc
    except anthropic.APIStatusError as exc:
        logger.exception("Anthropic a retourné une erreur HTTP")
        raise HTTPException(
            status_code=502,
            detail="Le service IA a rencontré une erreur. Veuillez réessayer.",
        ) from exc
    except anthropic.APIError as exc:
        logger.exception("Erreur du SDK Anthropic")
        raise HTTPException(
            status_code=502,
            detail="Le service IA a rencontré une erreur. Veuillez réessayer.",
        ) from exc
    except Exception as exc:
        logger.exception("Erreur inattendue pendant le traitement de /chat")
        raise HTTPException(
            status_code=500,
            detail="Une erreur interne est survenue. Veuillez réessayer.",
        ) from exc

    user = current_user(request, required=False)
    if user is not None:
        try:
            assign_plan_to_user(result["plan_id"], user["id"])
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


@app.delete("/history/accepted-actions/{action_id}")
def remove_accepted_action_history(action_id: int, request: Request) -> dict:
    """Masque une action uniquement dans l'historique du compte connecté."""
    user = current_user(request)
    try:
        return hide_accepted_action(user["id"], action_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/calendar/events")
def calendar_events(
    request: Request,
    start: date | None = None,
    end: date | None = None,
    plan_id: list[str] = Query(default=[]),
) -> dict:
    """Expose les événements PostgreSQL exécutés, avec un filtrage de période optionnel."""
    user = current_user(request, required=False)
    try:
        return {
            "events": list_calendar_events(
                start,
                end,
                user_id=user["id"] if user is not None else None,
                plan_ids=plan_id,
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/calendar/events/{event_id}")
def remove_calendar_event(
    event_id: int,
    request: Request,
    plan_id: str | None = None,
) -> dict:
    """Supprime un événement après une confirmation explicite dans le frontend."""
    user = current_user(request, required=False)
    try:
        return delete_calendar_event(
            event_id,
            user_id=user["id"] if user is not None else None,
            plan_id=plan_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/plans/latest")
def latest_plan(request: Request) -> dict:
    """Retrouve le dernier plan du compte connecté."""
    user = current_user(request)
    plan = get_latest_user_plan(user["id"])
    if plan is None:
        raise HTTPException(status_code=404, detail="Aucun plan trouvé")
    return plan


@app.get("/plans/{plan_id}")
def restore_plan(plan_id: str, request: Request) -> dict:
    """Reconstruit un plan persistant et ses actions après un rechargement de page."""
    plan = get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan introuvable")
    user = current_user(request, required=False)
    if plan["user_id"] is not None and (user is None or user["id"] != plan["user_id"]):
        raise HTTPException(status_code=404, detail="Plan introuvable")
    return plan


@app.get("/trace")
def trace(
    request: Request,
    limit: int = 20,
    plan_id: list[str] = Query(default=[]),
) -> dict:
    """Journal d'audit limité au compte ou aux plans anonymes connus du navigateur."""
    user = current_user(request, required=False)
    return {
        "calls": get_recent_audit_log(
            limit,
            user_id=user["id"] if user is not None else None,
            plan_ids=plan_id,
        )
    }


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
def approve_action(action_id: int, request: Request) -> dict:
    """Exécute une action uniquement après cette validation humaine explicite."""
    user = current_user(request, required=False)
    verify_action_access(action_id, user["id"] if user is not None else None)
    result = approve_pending_action(action_id)
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


@app.post("/actions/{action_id}/reject")
def reject_action(action_id: int, request: Request) -> dict:
    """Refuse une action en attente sans provoquer son effet de bord."""
    user = current_user(request, required=False)
    verify_action_access(action_id, user["id"] if user is not None else None)
    result = reject_pending_action(action_id)
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
