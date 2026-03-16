def run(transcript_data: dict, speaker_map: dict, guest_name: str | None = None) -> str:
    """
    s04: Merges transcript data with speaker map to create a labeled transcript.
    
    Args:
        transcript_data: dict from s02 containing 'words' or 'utterances' with text and timestamps
        speaker_map: dict mapping speaker IDs to roles and names (e.g., {"SPEAKER_0": {"role": "guest", "name": "Elon Musk"}})
        guest_name: optional string to use for guest speaker label
        
    Returns:
        Full labeled transcript as a single string
    """
    try:
        if not transcript_data:
            raise RuntimeError("transcript_data is empty")
            
        # Get utterances from transcript_data
        utterances = transcript_data.get("utterances", [])
        if not utterances:
            # If no utterances, maybe we can try to fall back to words, but usually Deepgram returns utterances.
            # Let's assume Deepgram format with utterances.
            raise RuntimeError("No utterances found in transcript_data")
            
        labeled_lines = []
        count = 0
        
        for utt in utterances:
            text = utt.get("transcript", "").strip()
            if not text:
                continue
                
            speaker_id = str(utt.get("speaker", ""))
            if not speaker_id and "SPEAKER_" not in speaker_id:
                # Format to SPEAKER_X if it's just an integer
                speaker_id = f"SPEAKER_{speaker_id}"
                
            # Parse speaker info
            speaker_info = speaker_map.get(speaker_id, {})
            role = speaker_info.get("role", "UNKNOWN").upper()
            name = speaker_info.get("name", "")
            
            # Override guest name if provided and role is GUEST
            if role == "GUEST" and guest_name:
                name = guest_name
                
            # Format speaker label
            if name:
                speaker_label = f"{role} ({name})"
            else:
                speaker_label = role
                
            # Format timestamp MM:SS.s
            start_sec = float(utt.get("start", 0.0))
            minutes = int(start_sec // 60)
            seconds = start_sec % 60
            timestamp = f"[{minutes:02d}:{seconds:04.1f}]"
            
            # Format sentiment
            sentiment_str = ""
            sentiment_score = utt.get("sentiment", 0.0)
            if sentiment_score is not None:
                try:
                    score = float(sentiment_score)
                    if abs(score) > 0.3:
                        sentiment_str = f" [sentiment:{score:.2f}]"
                except (ValueError, TypeError):
                    pass
                    
            line = f"{timestamp} {speaker_label}:{sentiment_str} {text}"
            labeled_lines.append(line)
            count += 1
            
        result_str = "\n".join(labeled_lines)
        print(f"[S04] Generated labeled transcript with {count} utterances")
        return result_str
        
    except RuntimeError as re:
        raise re
    except Exception as e:
        print(f"[S04] Error: {e}")
        # Reraise so orchestrator knows it failed, or return empty string?
        # Requirements say: "Full try/except, raises RuntimeError if transcript_data is empty"
        # We should probably raise so the pipeline step fails properly.
        raise RuntimeError(f"Failed to generate labeled transcript: {e}")
