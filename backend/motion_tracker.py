"""WebSocket motion tracker loop (MediaPipe + exercise heuristics)."""

from __future__ import annotations

import base64

import cv2
import mediapipe as mp
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from poses.lat_pulldown import analyze_lat_pulldown
from poses.squat import analyze_squat

EXERCISES = {
    "squat": analyze_squat,
    "lat_pulldown": analyze_lat_pulldown,
}


async def handle_motion_tracker(websocket: WebSocket, exercise_type: str):
    analyze = EXERCISES.get(exercise_type)
    if analyze is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    state = {}
    pose = mp.solutions.pose.Pose(model_complexity=1)

    try:
        while True:
            payload = await websocket.receive_json()
            raw = payload.get("frame", "")
            if "," in raw:
                raw = raw.split(",", 1)[1]

            image = cv2.imdecode(np.frombuffer(base64.b64decode(raw), np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                await websocket.send_json({"reps": state.get("reps", 0), "issues": []})
                continue

            results = pose.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            if not results.pose_landmarks:
                await websocket.send_json({"reps": state.get("reps", 0), "issues": [], "pose_detected": False})
                continue

            landmarks = [
                {"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
                for lm in results.pose_landmarks.landmark
            ]
            state, reps, issues = analyze(landmarks, state)
            await websocket.send_json({"reps": reps, "phase": state.get("phase"), "issues": issues, "pose_detected": True})
    except WebSocketDisconnect:
        pass
    finally:
        pose.close()
