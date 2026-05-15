from typing import Optional
from app.config import settings
import httpx
import os
import re


def _safe_keyterms(keyterms: Optional[list[str]]) -> list[str]:
    """Keep Deepgram keyterm hints small and safe enough to never block transcription."""
    if not keyterms:
        return []

    max_terms = int(os.getenv("DEEPGRAM_MAX_KEYTERMS", "25"))
    seen: set[str] = set()
    safe_terms: list[str] = []

    for raw in keyterms:
        term = str(raw or "").strip()
        if not term or len(term) > 60:
            continue
        if len(term.split()) > 4:
            continue
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9' ._-]*", term):
            continue

        key = term.lower()
        if key in seen:
            continue

        seen.add(key)
        safe_terms.append(term)
        if len(safe_terms) >= max_terms:
            break

    return safe_terms


def transcribe(audio_path: str, keyterms: Optional[list[str]] = None) -> dict:
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        headers = {
            "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
            "Content-Type": "audio/mp4"
        }

        # Nova-3 uses "keyterm" (repeated param) for domain-specific hint terms
        base_params = [
            ("model", "nova-3"),
            ("diarize", "true"),
            ("sentiment", "true"),
            ("punctuate", "true"),
            ("utterances", "true"),
            ("words", "true"),
            ("detect_language", "true"),
            ("multichannel", "false"),
        ]
        safe_keyterms = _safe_keyterms(keyterms)
        if safe_keyterms:
            for term in safe_keyterms:
                base_params.append(("keyterm", term))
            print(f"[Deepgram] Sending {len(safe_keyterms)} safe keyterms to Nova-3")

        response = httpx.post(
            "https://api.deepgram.com/v1/listen",
            headers=headers,
            params=base_params,
            content=audio_data,
            timeout=300.0
        )

        if response.status_code == 400 and safe_keyterms:
            print("[Deepgram] Keyterm request rejected; retrying Nova-3 without keyterms")
            retry_params = [item for item in base_params if item[0] != "keyterm"]
            response = httpx.post(
                "https://api.deepgram.com/v1/listen",
                headers=headers,
                params=retry_params,
                content=audio_data,
                timeout=300.0
            )

        response.raise_for_status()
        return response.json()

    except Exception as e:
        print(f"[Deepgram] Transcription failed: {e}")
        raise
