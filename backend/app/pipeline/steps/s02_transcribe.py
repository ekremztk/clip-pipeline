from app.services.deepgram_client import transcribe

def run(audio_path: str, job_id: str) -> dict:
    """
    Step 02: Transcribe
    Calls Deepgram to transcribe the audio file and returns structured data.
    """
    print(f"[S02] Starting transcription for job {job_id}, audio: {audio_path}")
    
    try:
        result = transcribe(audio_path)
        
        # Check if the transcription returned an empty transcript
        if not result or not result.get("transcript"):
            raise RuntimeError("Transcription returned empty transcript")
            
        word_count = len(result.get("words", []))
        duration = result.get("duration", 0.0)
        
        print(f"[S02] Transcription completed. Word count: {word_count}, duration: {duration}s")
        return result
        
    except Exception as e:
        print(f"[S02] Error: {e}")
        raise
