"""Functional lat pulldown form heuristics using MediaPipe Pose landmarks."""

from __future__ import annotations

from typing import Any

from poses.helpers import angle, lm, visible_enough


left_shoulder_i, right_shoulder_i = 11, 12
left_elbow_i, right_elbow_i = 13, 14
left_wrist_i, right_wrist_i = 15, 16
left_hip_i, right_hip_i = 23, 24

min_active_frames = 10
issue_cooldown_frames = 45


def analyze_lat_pulldown(
    landmarks: list, state: dict[str, Any] | None = None
) -> tuple[dict[str, Any], int, list[dict[str, str]]]:
    if state is None:
        state = {}

    phase = state.get("phase", "arms_up")
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

    left_pull_depth = left_wrist[1] - left_shoulder[1]
    right_pull_depth = right_wrist[1] - right_shoulder[1]
    pull_depth = (left_pull_depth + right_pull_depth) / 2.0

    if phase == "arms_up" and elbow_angle < 125:
        phase = "pulling"
        set_started = True
    elif phase == "pulling" and elbow_angle < 85:
        phase = "bottom"
    elif phase == "bottom" and elbow_angle > 105:
        phase = "returning"
    elif phase == "returning" and elbow_angle > 155:
        phase = "arms_up"
        reps += 1

    if phase in {"pulling", "bottom", "returning"}:
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

    if can_coach and phase in {"pulling", "bottom", "returning"}:
        if abs(left_elbow_angle - right_elbow_angle) > 30:
            emit(
                "asymmetry",
                f"uneven pull, left elbow {left_elbow_angle:.0f} vs right {right_elbow_angle:.0f}",
            )

        shoulder_width = abs(left_shoulder[0] - right_shoulder[0]) or 0.2
        left_flare = abs(left_elbow[0] - left_shoulder[0])
        right_flare = abs(right_elbow[0] - right_shoulder[0])
        if left_flare > shoulder_width * 0.95 or right_flare > shoulder_width * 0.95:
            emit("elbow_flare", "elbows flaring too far from the torso")

        if phase == "bottom" and pull_depth < 0.02:
            emit("shallow_pull", "bar not reaching near chest height")

        mid_shoulder_x = (left_shoulder[0] + right_shoulder[0]) / 2.0
        mid_hip_x = (left_hip[0] + right_hip[0]) / 2.0
        if abs(mid_shoulder_x - mid_hip_x) > 0.15:
            emit("lean_back", "torso leaning back instead of staying upright")

    new_state = {
        "phase": phase,
        "reps": reps,
        "issue_cooldown": cooldown,
        "frame": frame,
        "active_frames": active_frames,
        "set_started": set_started,
        "elbow_angle": elbow_angle,
        "pull_depth": pull_depth,
        "pose_ok": True,
    }
    return new_state, reps, issues
