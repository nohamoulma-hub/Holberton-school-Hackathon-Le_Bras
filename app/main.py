import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent import run_agent
from app.db import get_recent_audit_log, init_db

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

init_db()

app = FastAPI(title="Le Bras - Back")


class ChatRequest(BaseModel):
    message: str


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
    """Journal des derniers appels d'outils (idempotency_key, input, résultat/erreur) — pour
    montrer la séquence sans avoir besoin d'un print live."""
    return {"calls": get_recent_audit_log(limit)}


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
