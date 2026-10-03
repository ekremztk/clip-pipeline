from typing import Optional
from app.config import settings
import httpx
import os
import re
import time

# A stalled upload or read is a network hiccup, not a bad file: three jobs that
# started together once all died on "The write operation timed out" while jobs
# started five minutes later went through. Retry those; never retry 4xx.
_TRANSIENT = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)
_ATTEMPTS = 3
_TIMEOUT = httpx.Timeout(connect=30.0, write=300.0, read=600.0, pool=60.0)


def _post_with_retry(**kwargs) -> httpx.Response:
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            response = httpx.post("https://api.deepgram.com/v1/listen", timeout=_TIMEOUT, **kwargs)
            if response.status_code < 500 or attempt == _ATTEMPTS:
                return response
            print(f"[Deepgram] HTTP {response.status_code} on attempt {attempt}/{_ATTEMPTS}; retrying")
        except _TRANSIENT as e:
            if attempt == _ATTEMPTS:
                raise
            print(f"[Deepgram] {type(e).__name__} on attempt {attempt}/{_ATTEMPTS}: {e}; retrying")
        time.sleep(10 * attempt)


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

        response = _post_with_retry(
            headers=headers,
            params=base_params,
            content=audio_data,
        )

        if response.status_code == 400 and safe_keyterms:
            print("[Deepgram] Keyterm request rejected; retrying Nova-3 without keyterms")
            retry_params = [item for item in base_params if item[0] != "keyterm"]
            response = _post_with_retry(
                headers=headers,
                params=retry_params,
                content=audio_data,
            )

        response.raise_for_status()
        return response.json()

    except Exception as e:
        print(f"[Deepgram] Transcription failed: {e}")
        raise
