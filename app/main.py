import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Le Bras - Back")

client = anthropic.Anthropic()


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat")
def chat(body: ChatRequest) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY manquante (voir .env)")

    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": body.message}],
    )

    text = next((block.text for block in response.content if block.type == "text"), "")
    return {"response": text}


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
