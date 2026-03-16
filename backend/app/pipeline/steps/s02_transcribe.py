from app.services.deepgram_client import transcribe

def run(audio_path: str, job_id: str) -> dict:
    """
    Step 02: Transcribe
    Calls Deepgram to transcribe the audio file and returns structured data.
    """
    print(f"[S02] Starting transcription for job {job_id}, audio: {audio_path}")
    
    try:
        result = transcribe(audio_path)
        
        channels = result.get("results", {}).get("channels", [])
        if not channels:
            raise RuntimeError("Deepgram returned no channels")
        alternative = channels[0].get("alternatives", [{}])[0]
        transcript_text = alternative.get("transcript", "")
        words = alternative.get("words", [])
        utterances = result.get("results", {}).get("utterances", [])
        duration = result.get("metadata", {}).get("duration", 0)
        
        word_count = len(words)
        
        print(f"[S02] Transcription completed. Word count: {word_count}, duration: {duration}s")
        return {
            "transcript": transcript_text,
            "words": words,
            "utterances": utterances,
            "duration": duration,
            "raw_response": result
        }
        
    except Exception as e:
        print(f"[S02] Error: {e}")
        raise
