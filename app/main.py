import os

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Le Bras - Back")

client = anthropic.Anthropic()


class PingRequest(BaseModel):
    prompt: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/agent/ping")
def agent_ping(body: PingRequest) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY manquante (voir .env)")

    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": body.prompt}],
    )

    text = next((block.text for block in response.content if block.type == "text"), "")
    return {"response": text, "model": response.model}