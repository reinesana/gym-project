"""Functional shoulder press form heuristics using MediaPipe Pose landmarks."""

from __future__ import annotations

from typing import Any

from poses.helpers import angle, lm, visible_enough


left_shoulder_i, right_shoulder_i = 11, 12
left_elbow_i, right_elbow_i = 13, 14
left_wrist_i, right_wrist_i = 15, 16
left_hip_i, right_hip_i = 23, 24

min_active_frames = 8
issue_cooldown_frames = 45


def analyze_shoulder_press(
    landmarks: list, state: dict[str, Any] | None = None
) -> tuple[dict[str, Any], int, list[dict[str, str]]]:
    if state is None:
        state = {}

    # racked (elbows bent near shoulders) -> pressing -> lockout -> lowering
    phase = state.get("phase", "racked")
    reps = int(state.get("reps", 0))
    cooldown = dict(state.get("issue_cooldown", {}))
    frame = int(state.get("frame", 0)) + 1
    active_frames = int(state.get("active_frames", 0))
    set_started = bool(state.get("set_started", False))

    left_shoulder = lm(landmarks, left_shoulder_i)
    right_shoulder = lm(landmarks, right_shoulder_i)
    left_elbow = lm(landmarks, left_elbow_i)
    right_elbow = lm(landmarks, right_elbow_i)
    left_wrist = lm(landmarks, left_wrist_i)
    right_wrist = lm(landmarks, right_wrist_i)
    left_hip = lm(landmarks, left_hip_i)
    right_hip = lm(landmarks, right_hip_i)

    key_points = [left_shoulder, right_shoulder, left_elbow, right_elbow, left_wrist, right_wrist]
    if not visible_enough(key_points, 0.65):
        return {
            "phase": phase,
            "reps": reps,
            "issue_cooldown": cooldown,
            "frame": frame,
            "active_frames": 0,
            "set_started": set_started,
            "pose_ok": False,
        }, reps, []

    left_elbow_angle = angle(left_shoulder, left_elbow, left_wrist)
    right_elbow_angle = angle(right_shoulder, right_elbow, right_wrist)
    elbow_angle = (left_elbow_angle + right_elbow_angle) / 2.0

    # How high wrists are relative to shoulders (y grows downward)
    left_height = left_shoulder[1] - left_wrist[1]
    right_height = right_shoulder[1] - right_wrist[1]
    press_height = (left_height + right_height) / 2.0

    if phase == "racked" and (elbow_angle > 100 or press_height > 0.08):
        phase = "pressing"
        set_started = True
    elif phase == "pressing" and elbow_angle > 150 and press_height > 0.14:
        phase = "lockout"
    elif phase == "lockout" and elbow_angle < 130:
        phase = "lowering"
    elif phase == "lowering" and elbow_angle < 100 and press_height < 0.08:
        phase = "racked"
        reps += 1

    if phase in {"pressing", "lockout", "lowering"}:
        active_frames += 1
    else:
        active_frames = 0

    issues: list[dict[str, str]] = []

    def emit(issue_type: str, detail: str) -> None:
        last = cooldown.get(issue_type, -10_000)
        if frame - last < issue_cooldown_frames:
            return
        issues.append({"type": issue_type, "detail": detail})
        cooldown[issue_type] = frame

    can_coach = set_started and active_frames >= min_active_frames

    if can_coach and phase in {"pressing", "lockout", "lowering"}:
        if abs(left_elbow_angle - right_elbow_angle) > 28:
            emit(
                "asymmetry",
                f"uneven press, left {left_elbow_angle:.0f} vs right {right_elbow_angle:.0f}",
            )

        if phase == "lockout" and elbow_angle < 155:
            emit("soft_lockout", f"arms not finishing overhead, angle about {elbow_angle:.0f}")

        # Excessive arch / lean
        mid_shoulder_x = (left_shoulder[0] + right_shoulder[0]) / 2.0
        mid_hip_x = (left_hip[0] + right_hip[0]) / 2.0
        if abs(mid_shoulder_x - mid_hip_x) > 0.13:
            emit("lean_back", "leaning back instead of pressing straight up")

        # Wrists drifting too far outside shoulders
        shoulder_width = abs(left_shoulder[0] - right_shoulder[0]) or 0.2
        left_flare = abs(left_wrist[0] - left_shoulder[0])
        right_flare = abs(right_wrist[0] - right_shoulder[0])
        if left_flare > shoulder_width * 0.85 or right_flare > shoulder_width * 0.85:
            emit("wrist_flare", "hands drifting too wide over the shoulders")

    new_state = {
        "phase": phase,
        "reps": reps,
        "issue_cooldown": cooldown,
        "frame": frame,
        "active_frames": active_frames,
        "set_started": set_started,
        "elbow_angle": elbow_angle,
        "press_height": press_height,
        "pose_ok": True,
    }
    return new_state, reps, issues
