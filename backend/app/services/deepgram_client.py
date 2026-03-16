from deepgram import DeepgramClient, PrerecordedOptions, FileSource
from app.config import settings

def transcribe(audio_path: str) -> dict:
    print(f"[DeepgramClient] Starting transcription for {audio_path}")
    
    api_key = settings.DEEPGRAM_API_KEY
    if not api_key:
        print("[DeepgramClient] Error: DEEPGRAM_API_KEY is missing.")
        raise RuntimeError("DEEPGRAM_API_KEY is missing from settings.")
        
    try:
            
        deepgram = DeepgramClient(api_key)
        
        with open(audio_path, "rb") as audio:
            buffer_data = audio.read()
            
        payload: FileSource = {
            "buffer": buffer_data,
        }
        
        options = PrerecordedOptions(
            model="nova-2",
            diarize=True,
            sentiment=True,
            punctuate=True,
            utterances=True,
            words=True,
            language="en"
        )
        
        print("[DeepgramClient] Sending file to Deepgram API...")
        response = deepgram.listen.rest.v("1").transcribe_file(payload, options)
        
        print("[DeepgramClient] Parsing response...")
        
        # Parse the required fields
        channels = response.results.channels
        if not channels or not channels[0].alternatives:
            raise RuntimeError("Unexpected Deepgram response format: missing channels or alternatives.")
            
        alternative = channels[0].alternatives[0]
        
        # Process words
        parsed_words = []
        if hasattr(alternative, 'words') and alternative.words:
            for w in alternative.words:
                parsed_words.append({
                    "word": getattr(w, "word", ""),
                    "start": getattr(w, "start", 0.0),
                    "end": getattr(w, "end", 0.0),
                    "speaker": str(getattr(w, "speaker", "")),
                    "confidence": getattr(w, "confidence", 0.0)
                })
                
        # Process utterances
        parsed_utterances = []
        if hasattr(response.results, 'utterances') and response.results.utterances:
            for u in response.results.utterances:
                parsed_utterances.append({
                    "speaker": str(getattr(u, "speaker", "")),
                    "start": getattr(u, "start", 0.0),
                    "end": getattr(u, "end", 0.0),
                    "text": getattr(u, "text", getattr(u, "transcript", "")),
                    "sentiment": getattr(u, "sentiment", ""),
                    "sentiment_score": getattr(u, "sentiment_score", 0.0)
                })
                
        result = {
            "words": parsed_words,
            "utterances": parsed_utterances,
            "transcript": getattr(alternative, "transcript", ""),
            "duration": getattr(response.metadata, "duration", 0.0)
        }
        
        print("[DeepgramClient] Transcription completed successfully.")
        return result
        
    except Exception as e:
        print(f"[DeepgramClient] Error during transcription: {e}")
        raise
