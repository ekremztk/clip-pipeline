from typing import Optional
from app.config import settings
import httpx


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
        if keyterms:
            for term in keyterms:
                base_params.append(("keyterm", term))
            print(f"[Deepgram] Sending {len(keyterms)} keyterms to Nova-3")

        response = httpx.post(
            "https://api.deepgram.com/v1/listen",
            headers=headers,
            params=base_params,
            content=audio_data,
            timeout=300.0
        )

        response.raise_for_status()
        return response.json()

    except Exception as e:
        print(f"[Deepgram] Transcription failed: {e}")
        raise
