from deepgram import DeepgramClient
from app.config import settings
import httpx

def transcribe(audio_path: str) -> dict:
    try:
        client = DeepgramClient(api_key=settings.DEEPGRAM_API_KEY)
        
        with open(audio_path, "rb") as audio_file:
            buffer_data = audio_file.read()
        
        payload = {"buffer": buffer_data}
        
        options = {
            "model": "nova-2",
            "diarize": True,
            "sentiment": True,
            "punctuate": True,
            "utterances": True,
            "words": True,
            "language": "en"
        }
        
        response = client.listen.prerecorded.v("1").transcribe_file(
            payload, options
        )
        
        return response.to_dict()
        
    except Exception as e:
        print(f"[Deepgram] Transcription failed: {e}")
        raise
