"""Live mid-set coaching lines from OpenAI (not called every video frame)."""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI


system_prompt = (
    "You are Gym Nerd 3000, a live personal trainer talking through the browser. "
    "Given one form issue detected mid-set, reply with ONE short spoken cue only: "
    "max 12 words, varied wording, energetic, specific to the detail provided. "
    "Do not greet, do not use markdown or emoji, do not repeat prior cues if listed."
)


def generate_live_cue(payload: dict[str, Any]) -> str:
    """
    Turn a detected issue into a fresh spoken coaching line.
    Called only when the frontend debounces a real form break after the set starts.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    exercise = payload.get("exercise", "exercise")
    issue_type = payload.get("issue_type", "form")
    detail = payload.get("detail", "")
    phase = payload.get("phase", "")
    reps = payload.get("reps", 0)
    recent = payload.get("recent_cues") or []

    user_content = (
        f"Exercise: {exercise}. Phase: {phase}. Reps so far: {reps}. "
        f"Issue type: {issue_type}. Detail: {detail}. "
        f"Recent cues already said: {recent}. "
        "Give a new short coaching cue now."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.95,
        max_tokens=40,
    )
    text = (response.choices[0].message.content or "").strip().strip('"')
    return text or "Reset your form and keep going."
