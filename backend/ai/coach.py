"""Post-set OpenAI coaching summaries (not used in the real-time video loop)."""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI


SYSTEM_PROMPT = (
    "You are an energetic, supportive personal fitness coach. "
    "Given the user's completed set (reps and any form issues), write a short "
    "post-set voice summary: 2–4 sentences, encouraging, specific, and actionable. "
    "Do not use markdown, bullet lists, or emoji. Speak directly to the athlete."
)


def generate_coach_summary(chat_history: list[dict[str, Any]]) -> str:
    """
    Accept a chat message history, prepend the coach system prompt, and return
    a short GPT-4o-mini post-set summary.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for message in chat_history:
        role = str(message.get("role", "user"))
        content = str(message.get("content", ""))
        if role not in {"system", "user", "assistant"}:
            role = "user"
        if content:
            messages.append({"role": role, "content": content})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=220,
    )
    return (response.choices[0].message.content or "").strip()
