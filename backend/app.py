"""
FastAPI server for real-time form checking (MediaPipe + math) and post-set AI coaching.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ai.coach import generate_coach_summary
from poses.lat_pulldown import analyze_lat_pulldown
from poses.squat import analyze_squat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("formcheck")

app = FastAPI(title="AI Fitness Form Coach")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXERCISE_ANALYZERS = {
    "squat": analyze_squat,
    "lat_pulldown": analyze_lat_pulldown,
}

mp_pose = mp.solutions.pose


class CoachSummaryRequest(BaseModel):
    chat_history: list[dict[str, Any]] = Field(default_factory=list)


class CoachSummaryResponse(BaseModel):
    summary: str


def _decode_jpeg_frame(payload: dict[str, Any]) -> np.ndarray | None:
    """Decode a Base64 JPEG (optionally data-URL prefixed) into a BGR image."""
    raw = payload.get("frame") or payload.get("image") or payload.get("data")
    if not raw or not isinstance(raw, str):
        return None
    if "," in raw and raw.strip().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        binary = base64.b64decode(raw)
    except Exception:
        return None
    arr = np.frombuffer(binary, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return image


def _landmarks_to_list(landmark_list) -> list[dict[str, float]]:
    return [
        {"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
        for lm in landmark_list.landmark
    ]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/coach-summary", response_model=CoachSummaryResponse)
def coach_summary(body: CoachSummaryRequest) -> CoachSummaryResponse:
    """Generate a personalized post-set voice summary via OpenAI (once per set)."""
    summary = generate_coach_summary(body.chat_history)
    return CoachSummaryResponse(summary=summary)


@app.websocket("/ws/formcheck/{exercise_type}")
async def formcheck_ws(websocket: WebSocket, exercise_type: str) -> None:
    """
    Real-time form check loop.
    Expects JSON messages with a Base64 JPEG in `frame`.
    Responds with {reps, phase, issues: [{type, spoken_text}], ...}.
    """
    analyzer = EXERCISE_ANALYZERS.get(exercise_type)
    if analyzer is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    state: dict[str, Any] = {}

    with mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:
        try:
            while True:
                payload = await websocket.receive_json()
                image = _decode_jpeg_frame(payload)
                if image is None:
                    await websocket.send_json(
                        {
                            "reps": int(state.get("reps", 0)),
                            "issues": [],
                            "error": "invalid_frame",
                        }
                    )
                    continue

                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                results = pose.process(rgb)

                if not results.pose_landmarks:
                    await websocket.send_json(
                        {
                            "reps": int(state.get("reps", 0)),
                            "phase": state.get("phase"),
                            "issues": [],
                            "pose_detected": False,
                        }
                    )
                    continue

                landmarks = _landmarks_to_list(results.pose_landmarks)
                state, reps, issues = analyzer(landmarks, state)
                await websocket.send_json(
                    {
                        "reps": reps,
                        "phase": state.get("phase"),
                        "issues": issues,
                        "pose_detected": True,
                    }
                )
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected (%s)", exercise_type)
        except Exception:
            logger.exception("WebSocket error (%s)", exercise_type)
            try:
                await websocket.close(code=1011)
            except Exception:
                pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
