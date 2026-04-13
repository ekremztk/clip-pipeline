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

        # Note: Nova-3 does not support the keywords parameter — skip keyterm injection
        if keyterms:
            print(f"[Deepgram] Keyterms provided ({len(keyterms)}) but skipped — not supported by Nova-3")

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
