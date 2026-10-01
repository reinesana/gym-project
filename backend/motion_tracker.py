"""WebSocket motion tracker loop (MediaPipe + exercise heuristics)."""

from __future__ import annotations

import base64

import cv2
import mediapipe as mp
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from poses.bicep_curl import analyze_bicep_curl
from poses.lat_pulldown import analyze_lat_pulldown
from poses.shoulder_press import analyze_shoulder_press
from poses.squat import analyze_squat

exercises = {
    "squat": analyze_squat,
    "lat_pulldown": analyze_lat_pulldown,
    "bicep_curl": analyze_bicep_curl,
    "shoulder_press": analyze_shoulder_press,
}


async def handle_motion_tracker(websocket: WebSocket, exercise_type: str):
    analyze = exercises.get(exercise_type)
    if analyze is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    state = {}
    pose = mp.solutions.pose.Pose(
        model_complexity=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
    )

    try:
        while True:
            payload = await websocket.receive_json()
            raw = payload.get("frame", "")
            if "," in raw:
                raw = raw.split(",", 1)[1]

            image = cv2.imdecode(np.frombuffer(base64.b64decode(raw), np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                await websocket.send_json({"reps": state.get("reps", 0), "issues": [], "landmarks": []})
                continue

            results = pose.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            if not results.pose_landmarks:
                await websocket.send_json(
                    {"reps": state.get("reps", 0), "issues": [], "pose_detected": False, "landmarks": []}
                )
                continue

            landmarks = [
                {"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
                for lm in results.pose_landmarks.landmark
            ]
            state, reps, issues = analyze(landmarks, state)
            await websocket.send_json(
                {
                    "reps": reps,
                    "phase": state.get("phase"),
                    "issues": issues,
                    "pose_detected": True,
                    "set_started": bool(state.get("set_started")),
                    "landmarks": landmarks,
                }
            )
    except WebSocketDisconnect:
        pass
    finally:
        pose.close()
