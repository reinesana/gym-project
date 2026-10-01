"""Functional lat pulldown form heuristics using MediaPipe Pose landmarks."""

from __future__ import annotations

import math
from typing import Any


# MediaPipe landmark indices
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_ELBOW, RIGHT_ELBOW = 13, 14
LEFT_WRIST, RIGHT_WRIST = 15, 16
LEFT_HIP, RIGHT_HIP = 23, 24


def _lm(landmarks: list, index: int) -> tuple[float, float, float]:
    point = landmarks[index]
    if isinstance(point, dict):
        return float(point["x"]), float(point["y"]), float(point.get("visibility", 1.0))
    return float(point.x), float(point.y), float(getattr(point, "visibility", 1.0))


def _angle(a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]) -> float:
    """Return the angle ABC in degrees."""
    bax, bay = a[0] - b[0], a[1] - b[1]
    bcx, bcy = c[0] - b[0], c[1] - b[1]
    dot = bax * bcx + bay * bcy
    mag_a = math.hypot(bax, bay)
    mag_c = math.hypot(bcx, bcy)
    if mag_a * mag_c == 0:
        return 180.0
    cos_angle = max(-1.0, min(1.0, dot / (mag_a * mag_c)))
    return math.degrees(math.acos(cos_angle))


def analyze_lat_pulldown(
    landmarks: list, state: dict[str, Any] | None = None
) -> tuple[dict[str, Any], int, list[dict[str, str]]]:
    """
    Analyze one frame of lat pulldown pose.

    Returns:
        new_state: updated tracking state
        rep_count: total completed reps
        issues: list of {type, spoken_text} for form breaks
    """
    if state is None:
        state = {}

    # arms_up (start) -> pulling -> bottom -> returning
    phase = state.get("phase", "arms_up")
    reps = int(state.get("reps", 0))
    cooldown = dict(state.get("issue_cooldown", {}))
    frame = int(state.get("frame", 0)) + 1

    left_shoulder = _lm(landmarks, LEFT_SHOULDER)
    right_shoulder = _lm(landmarks, RIGHT_SHOULDER)
    left_elbow = _lm(landmarks, LEFT_ELBOW)
    right_elbow = _lm(landmarks, RIGHT_ELBOW)
    left_wrist = _lm(landmarks, LEFT_WRIST)
    right_wrist = _lm(landmarks, RIGHT_WRIST)
    left_hip = _lm(landmarks, LEFT_HIP)
    right_hip = _lm(landmarks, RIGHT_HIP)

    left_elbow_angle = _angle(left_shoulder, left_elbow, left_wrist)
    right_elbow_angle = _angle(right_shoulder, right_elbow, right_wrist)
    elbow_angle = (left_elbow_angle + right_elbow_angle) / 2.0

    # Shoulder abduction-ish: wrist height relative to shoulder (y grows downward)
    left_pull_depth = left_wrist[1] - left_shoulder[1]
    right_pull_depth = right_wrist[1] - right_shoulder[1]
    pull_depth = (left_pull_depth + right_pull_depth) / 2.0

    issues: list[dict[str, str]] = []

    def _emit(issue_type: str, spoken_text: str, every_n_frames: int = 30) -> None:
        last = cooldown.get(issue_type, -10_000)
        if frame - last >= every_n_frames:
            issues.append({"type": issue_type, "spoken_text": spoken_text})
            cooldown[issue_type] = frame

    # Rep state machine: arms extended (high elbow angle) → pulled (low angle) → extend
    if phase == "arms_up" and elbow_angle < 140:
        phase = "pulling"
    elif phase == "pulling" and elbow_angle < 90:
        phase = "bottom"
    elif phase == "bottom" and elbow_angle > 110:
        phase = "returning"
    elif phase == "returning" and elbow_angle > 150:
        phase = "arms_up"
        reps += 1

    if phase in {"pulling", "bottom", "returning"}:
        # Uneven pull between sides
        if abs(left_elbow_angle - right_elbow_angle) > 25:
            _emit("asymmetry", "Pull evenly with both arms")

        # Elbows flaring too far from torso in image x-space
        shoulder_width = abs(left_shoulder[0] - right_shoulder[0]) or 0.2
        left_flare = abs(left_elbow[0] - left_shoulder[0])
        right_flare = abs(right_elbow[0] - right_shoulder[0])
        if left_flare > shoulder_width * 0.85 or right_flare > shoulder_width * 0.85:
            _emit("elbow_flare", "Keep your elbows closer to your sides")

        # Incomplete range — wrists never drop near chest/shoulder line
        if phase == "bottom" and pull_depth < 0.05:
            _emit("shallow_pull", "Pull the bar down to your chest")

        # Leaning too far back: shoulders drifting behind hips
        mid_shoulder_x = (left_shoulder[0] + right_shoulder[0]) / 2.0
        mid_hip_x = (left_hip[0] + right_hip[0]) / 2.0
        if abs(mid_shoulder_x - mid_hip_x) > 0.12:
            _emit("lean_back", "Stay upright, don't lean back")

    new_state = {
        "phase": phase,
        "reps": reps,
        "issue_cooldown": cooldown,
        "frame": frame,
        "elbow_angle": elbow_angle,
        "pull_depth": pull_depth,
    }
    return new_state, reps, issues
