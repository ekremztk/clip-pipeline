"""Robust JSON extraction helpers for model responses."""
from __future__ import annotations

import json
import re
from typing import Any


def parse_json_list_response(raw: str, *, log_prefix: str = "[JSON]") -> list[dict[str, Any]]:
    """Extract the first valid JSON list from an LLM response.

    Models sometimes return valid JSON followed by extra prose or a second draft.
    ``json.loads`` rejects that with "Extra data"; ``raw_decode`` lets us keep the
    first valid JSON value and ignore trailing text.
    """
    if not raw:
        return []

    cleaned = _strip_markdown_fence(raw.strip())
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)

    decoder = json.JSONDecoder()
    for start in _json_start_positions(cleaned):
        try:
            value, _ = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError:
            continue

        parsed = _coerce_to_list(value)
        if parsed:
            return parsed

    try:
        value = json.loads(cleaned)
        return _coerce_to_list(value)
    except json.JSONDecodeError as exc:
        print(f"{log_prefix} JSON parse error: {exc}")
        print(f"{log_prefix} Raw snippet: {cleaned[:400]}")
        return []


def _strip_markdown_fence(text: str) -> str:
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1)
    if text.endswith("```"):
        text = re.sub(r"\s*```$", "", text, count=1)
    return text.strip()


def _json_start_positions(text: str) -> list[int]:
    positions = [idx for idx, char in enumerate(text) if char in "[{"]
    bracket_positions = [idx for idx in positions if text[idx] == "["]
    object_positions = [idx for idx in positions if text[idx] == "{"]
    return bracket_positions + object_positions


def _coerce_to_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]

    if isinstance(value, dict):
        for key in ("candidates", "evaluated", "results", "items"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]

    return []

