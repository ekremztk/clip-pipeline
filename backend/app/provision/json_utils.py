from __future__ import annotations

import json
import re
from typing import Any


def parse_json_object(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from a model response."""
    if not raw:
        return {}

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1)
    if text.endswith("```"):
        text = re.sub(r"\s*```$", "", text, count=1)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()

    decoder = json.JSONDecoder()
    starts = [idx for idx, char in enumerate(text) if char == "{"]
    for start in starts:
        try:
            value, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    return {}


def compact_words(words: list[dict[str, Any]], limit: int = 900) -> list[dict[str, Any]]:
    """Keep only the word timing fields needed by the edit planner."""
    compact: list[dict[str, Any]] = []
    for word in words[:limit]:
        text = word.get("punctuated_word") or word.get("word") or ""
        if not text:
            continue
        compact.append(
            {
                "word": str(text),
                "start": round(float(word.get("start") or 0), 3),
                "end": round(float(word.get("end") or 0), 3),
            }
        )
    return compact

