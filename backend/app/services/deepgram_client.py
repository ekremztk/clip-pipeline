from app.config import settings
import httpx

def transcribe(audio_path: str) -> dict:
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        headers = {
            "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
            "Content-Type": "audio/mp4"
        }

        params = {
            "model": "nova-2",
            "diarize": "true",
            "sentiment": "true",
            "punctuate": "true",
            "utterances": "true",
            "words": "true",
            "detect_language": "true",
        }

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
