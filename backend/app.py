"""FastAPI entrypoint — routes only. Logic lives in motion_tracker / ai modules."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from ai.coach import generate_coach_summary
from ai.live_cue import generate_live_cue
from motion_tracker import handle_motion_tracker

load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gym_nerd")

app = FastAPI(title="Gym Nerd 3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "app": "Gym Nerd 3000"}


@app.post("/api/live-cue")
def live_cue(body: dict):
    """Generate one fresh mid-set coaching line (debounced by the client)."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")
    try:
        cue = generate_live_cue(body)
    except Exception as exc:
        logger.exception("live cue failed")
        raise HTTPException(status_code=502, detail=f"OpenAI request failed: {exc}") from exc
    return {"cue": cue}


@app.post("/api/coach-summary")
def coach_summary(body: dict):
    """Generate a personalized post-set voice summary via OpenAI (once per set)."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")

    chat_history = body.get("chat_history") or []
    try:
        summary = generate_coach_summary(chat_history)
    except Exception as exc:
        logger.exception("coach summary failed")
        raise HTTPException(status_code=502, detail=f"OpenAI request failed: {exc}") from exc

    return {"summary": summary}


@app.websocket("/ws/motion_tracker/{exercise_type}")
async def motion_tracker_ws(websocket: WebSocket, exercise_type: str):
    await handle_motion_tracker(websocket, exercise_type)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
