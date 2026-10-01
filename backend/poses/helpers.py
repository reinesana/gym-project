"""Shared pose math helpers (functional)."""

from __future__ import annotations

import math


def lm(landmarks: list, index: int) -> tuple[float, float, float]:
    point = landmarks[index]
    if isinstance(point, dict):
        return float(point["x"]), float(point["y"]), float(point.get("visibility", 1.0))
    return float(point.x), float(point.y), float(getattr(point, "visibility", 1.0))


def angle(a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]) -> float:
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


def visible_enough(points: list[tuple[float, float, float]], threshold: float = 0.65) -> bool:
    """Require joints to be confidently visible before judging form (MSU-style)."""
    return all(p[2] >= threshold for p in points)
