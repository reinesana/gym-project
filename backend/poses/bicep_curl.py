"""Functional bicep curl form heuristics using MediaPipe Pose landmarks."""

from __future__ import annotations

from typing import Any

from poses.helpers import angle, lm, visible_enough


left_shoulder_i, right_shoulder_i = 11, 12
left_elbow_i, right_elbow_i = 13, 14
left_wrist_i, right_wrist_i = 15, 16
left_hip_i, right_hip_i = 23, 24

min_active_frames = 8
issue_cooldown_frames = 45


def analyze_bicep_curl(
    landmarks: list, state: dict[str, Any] | None = None
) -> tuple[dict[str, Any], int, list[dict[str, str]]]:
    if state is None:
        state = {}

    # arms_down -> curling -> top -> lowering
    phase = state.get("phase", "arms_down")
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

    # Upper-arm drift vs vertical-ish shoulder→hip line (loose elbows swinging)
    left_upper = angle(left_hip, left_shoulder, left_elbow)
    right_upper = angle(right_hip, right_shoulder, right_elbow)
    upper_arm_swing = (left_upper + right_upper) / 2.0

    if phase == "arms_down" and elbow_angle < 120:
        phase = "curling"
        set_started = True
    elif phase == "curling" and elbow_angle < 70:
        phase = "top"
    elif phase == "top" and elbow_angle > 95:
        phase = "lowering"
    elif phase == "lowering" and elbow_angle > 145:
        phase = "arms_down"
        reps += 1

    if phase in {"curling", "top", "lowering"}:
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

    if can_coach and phase in {"curling", "top", "lowering"}:
        if abs(left_elbow_angle - right_elbow_angle) > 28:
            emit(
                "asymmetry",
                f"uneven curl, left {left_elbow_angle:.0f} vs right {right_elbow_angle:.0f}",
            )

        # Elbows drifting forward / swinging the upper arm
        if upper_arm_swing > 45:
            emit("elbow_swing", f"upper arms swinging, angle about {upper_arm_swing:.0f}")

        if phase == "top" and elbow_angle > 75:
            emit("shallow_curl", f"curl peak only reached about {elbow_angle:.0f} degrees")

        # Using momentum / leaning back
        mid_shoulder_x = (left_shoulder[0] + right_shoulder[0]) / 2.0
        mid_hip_x = (left_hip[0] + right_hip[0]) / 2.0
        if abs(mid_shoulder_x - mid_hip_x) > 0.12:
            emit("lean_back", "torso rocking to help swing the weight up")

    new_state = {
        "phase": phase,
        "reps": reps,
        "issue_cooldown": cooldown,
        "frame": frame,
        "active_frames": active_frames,
        "set_started": set_started,
        "elbow_angle": elbow_angle,
        "upper_arm_swing": upper_arm_swing,
        "pose_ok": True,
    }
    return new_state, reps, issues
