"""Functional squat form heuristics using MediaPipe Pose landmarks."""

from __future__ import annotations

import math
from typing import Any


# MediaPipe landmark indices
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_KNEE, RIGHT_KNEE = 25, 26
LEFT_ANKLE, RIGHT_ANKLE = 27, 28


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


def _knee_valgus(hip: tuple[float, float, float], knee: tuple[float, float, float], ankle: tuple[float, float, float], side: str) -> bool:
    """Detect knees caving inward relative to hip–ankle line."""
    if side == "left":
        # Knee x should not drift too far right of the hip–ankle midline
        midline = (hip[0] + ankle[0]) / 2.0
        return knee[0] > midline + 0.03
    midline = (hip[0] + ankle[0]) / 2.0
    return knee[0] < midline - 0.03


def analyze_squat(landmarks: list, state: dict[str, Any] | None = None) -> tuple[dict[str, Any], int, list[dict[str, str]]]:
    """
    Analyze one frame of squat pose.

    Returns:
        new_state: updated tracking state
        rep_count: total completed reps
        issues: list of {type, spoken_text} for form breaks
    """
    if state is None:
        state = {}

    phase = state.get("phase", "standing")  # standing | descending | bottom | ascending
    reps = int(state.get("reps", 0))
    cooldown = dict(state.get("issue_cooldown", {}))
    frame = int(state.get("frame", 0)) + 1

    left_shoulder = _lm(landmarks, LEFT_SHOULDER)
    right_shoulder = _lm(landmarks, RIGHT_SHOULDER)
    left_hip = _lm(landmarks, LEFT_HIP)
    right_hip = _lm(landmarks, RIGHT_HIP)
    left_knee = _lm(landmarks, LEFT_KNEE)
    right_knee = _lm(landmarks, RIGHT_KNEE)
    left_ankle = _lm(landmarks, LEFT_ANKLE)
    right_ankle = _lm(landmarks, RIGHT_ANKLE)

    left_knee_angle = _angle(left_hip, left_knee, left_ankle)
    right_knee_angle = _angle(right_hip, right_knee, right_ankle)
    knee_angle = (left_knee_angle + right_knee_angle) / 2.0

    torso_left = _angle(left_shoulder, left_hip, left_knee)
    torso_right = _angle(right_shoulder, right_hip, right_knee)
    torso_angle = (torso_left + torso_right) / 2.0

    issues: list[dict[str, str]] = []

    def _emit(issue_type: str, spoken_text: str, every_n_frames: int = 30) -> None:
        last = cooldown.get(issue_type, -10_000)
        if frame - last >= every_n_frames:
            issues.append({"type": issue_type, "spoken_text": spoken_text})
            cooldown[issue_type] = frame

    # Rep state machine based on average knee flexion
    if phase == "standing" and knee_angle < 140:
        phase = "descending"
    elif phase == "descending" and knee_angle < 100:
        phase = "bottom"
    elif phase == "bottom" and knee_angle > 120:
        phase = "ascending"
    elif phase == "ascending" and knee_angle > 155:
        phase = "standing"
        reps += 1

    # Form checks while under load (not fully standing)
    if phase in {"descending", "bottom", "ascending"}:
        if _knee_valgus(left_hip, left_knee, left_ankle, "left") or _knee_valgus(
            right_hip, right_knee, right_ankle, "right"
        ):
            _emit("knee_cave", "Push your knees out")

        if torso_angle < 55:
            _emit("forward_lean", "Keep your chest up")

        if phase == "bottom" and knee_angle > 105:
            _emit("shallow_depth", "Go a little deeper")

        hip_y = (left_hip[1] + right_hip[1]) / 2.0
        knee_y = (left_knee[1] + right_knee[1]) / 2.0
        if phase == "bottom" and hip_y < knee_y - 0.08:
            # Hips too high relative to knees in image space (y grows downward)
            _emit("hips_high", "Sit your hips lower")

    new_state = {
        "phase": phase,
        "reps": reps,
        "issue_cooldown": cooldown,
        "frame": frame,
        "knee_angle": knee_angle,
        "torso_angle": torso_angle,
    }
    return new_state, reps, issues
