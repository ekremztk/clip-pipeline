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

        params = {
            "model": "nova-3",
            "diarize": "true",
            "sentiment": "true",
            "punctuate": "true",
            "utterances": "true",
            "words": "true",
            "detect_language": "true",
            "multichannel": "false",
        }

        # Nova-3 keyterm prompting — boosts recognition of domain-specific words
        if keyterms:
            trimmed = [t.strip() for t in keyterms if t and t.strip()][:100]
            if trimmed:
                params["keywords"] = trimmed
                print(f"[Deepgram] Keyterms injected: {len(trimmed)} terms")

        response = httpx.post(
            "https://api.deepgram.com/v1/listen",
            headers=headers,
            params=params,
            content=audio_data,
            timeout=300.0
        )

        response.raise_for_status()
        return response.json()

    except Exception as e:
        print(f"[Deepgram] Transcription failed: {e}")
        raise
