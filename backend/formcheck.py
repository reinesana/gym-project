"""Real-time form-check helpers (functional — no classes)."""

from __future__ import annotations

import base64
import logging
from typing import Any, Callable

import cv2
import mediapipe as mp
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from poses.lat_pulldown import analyze_lat_pulldown
from poses.squat import analyze_squat

logger = logging.getLogger("formcheck")

EXERCISE_ANALYZERS: dict[str, Callable] = {
    "squat": analyze_squat,
    "lat_pulldown": analyze_lat_pulldown,
}

mp_pose = mp.solutions.pose


def decode_jpeg_frame(payload: dict[str, Any]) -> np.ndarray | None:
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
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def landmarks_to_list(landmark_list) -> list[dict[str, float]]:
    return [
        {"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
        for lm in landmark_list.landmark
    ]


def analyze_frame(
    pose,
    analyzer: Callable,
    state: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Run one frame through MediaPipe + the exercise heuristic.

    Returns (new_state, response_dict).
    """
    image = decode_jpeg_frame(payload)
    if image is None:
        return state, {
            "reps": int(state.get("reps", 0)),
            "issues": [],
            "error": "invalid_frame",
        }

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = pose.process(rgb)

    if not results.pose_landmarks:
        return state, {
            "reps": int(state.get("reps", 0)),
            "phase": state.get("phase"),
            "issues": [],
            "pose_detected": False,
        }

    landmarks = landmarks_to_list(results.pose_landmarks)
    new_state, reps, issues = analyzer(landmarks, state)
    return new_state, {
        "reps": reps,
        "phase": new_state.get("phase"),
        "issues": issues,
        "pose_detected": True,
    }


async def handle_formcheck(websocket: WebSocket, exercise_type: str) -> None:
    """Accept a WebSocket and stream form-check results until disconnect."""
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
                state, response = analyze_frame(pose, analyzer, state, payload)
                await websocket.send_json(response)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected (%s)", exercise_type)
        except Exception:
            logger.exception("WebSocket error (%s)", exercise_type)
            try:
                await websocket.close(code=1011)
            except Exception:
                pass
