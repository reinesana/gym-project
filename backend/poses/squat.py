"""Functional squat form heuristics using MediaPipe Pose landmarks."""

from __future__ import annotations

from typing import Any

from poses.helpers import angle, lm, visible_enough


left_shoulder_i, right_shoulder_i = 11, 12
left_hip_i, right_hip_i = 23, 24
left_knee_i, right_knee_i = 25, 26
left_ankle_i, right_ankle_i = 27, 28

# Only coach after the athlete has been moving for a bit
min_active_frames = 10
issue_cooldown_frames = 45


def knee_valgus(hip, knee, ankle, side: str) -> bool:
    midline = (hip[0] + ankle[0]) / 2.0
    if side == "left":
        return knee[0] > midline + 0.055
    return knee[0] < midline - 0.055


def analyze_squat(landmarks: list, state: dict[str, Any] | None = None) -> tuple[dict[str, Any], int, list[dict[str, str]]]:
    if state is None:
        state = {}

    phase = state.get("phase", "standing")
    reps = int(state.get("reps", 0))
    cooldown = dict(state.get("issue_cooldown", {}))
    frame = int(state.get("frame", 0)) + 1
    active_frames = int(state.get("active_frames", 0))
    set_started = bool(state.get("set_started", False))

    left_shoulder = lm(landmarks, left_shoulder_i)
    right_shoulder = lm(landmarks, right_shoulder_i)
    left_hip = lm(landmarks, left_hip_i)
    right_hip = lm(landmarks, right_hip_i)
    left_knee = lm(landmarks, left_knee_i)
    right_knee = lm(landmarks, right_knee_i)
    left_ankle = lm(landmarks, left_ankle_i)
    right_ankle = lm(landmarks, right_ankle_i)

    key_points = [left_hip, right_hip, left_knee, right_knee, left_ankle, right_ankle]
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

    left_knee_angle = angle(left_hip, left_knee, left_ankle)
    right_knee_angle = angle(right_hip, right_knee, right_ankle)
    knee_angle = (left_knee_angle + right_knee_angle) / 2.0

    torso_left = angle(left_shoulder, left_hip, left_knee)
    torso_right = angle(right_shoulder, right_hip, right_knee)
    torso_angle = (torso_left + torso_right) / 2.0

    # Stricter phase machine so setup/standing around doesn't look like a rep
    if phase == "standing" and knee_angle < 125:
        phase = "descending"
        set_started = True
    elif phase == "descending" and knee_angle < 95:
        phase = "bottom"
    elif phase == "bottom" and knee_angle > 115:
        phase = "ascending"
    elif phase == "ascending" and knee_angle > 160:
        phase = "standing"
        reps += 1

    if phase in {"descending", "bottom", "ascending"}:
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

    # No coaching until the set is clearly underway
    can_coach = set_started and active_frames >= min_active_frames

    if can_coach and phase in {"descending", "bottom", "ascending"}:
        if knee_valgus(left_hip, left_knee, left_ankle, "left") or knee_valgus(
            right_hip, right_knee, right_ankle, "right"
        ):
            emit("knee_cave", f"knees caving in at about {knee_angle:.0f} degrees of bend")

        if phase in {"descending", "bottom"} and torso_angle < 48:
            emit("forward_lean", f"chest dropping forward, torso angle about {torso_angle:.0f}")

        if phase == "bottom" and knee_angle > 108:
            emit("shallow_depth", f"squat depth only to about {knee_angle:.0f} degrees")

        hip_y = (left_hip[1] + right_hip[1]) / 2.0
        knee_y = (left_knee[1] + right_knee[1]) / 2.0
        if phase == "bottom" and hip_y < knee_y - 0.1:
            emit("hips_high", "hips staying high at the bottom of the squat")

    new_state = {
        "phase": phase,
        "reps": reps,
        "issue_cooldown": cooldown,
        "frame": frame,
        "active_frames": active_frames,
        "set_started": set_started,
        "knee_angle": knee_angle,
        "torso_angle": torso_angle,
        "pose_ok": True,
    }
    return new_state, reps, issues
