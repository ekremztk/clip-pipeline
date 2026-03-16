def run(transcript_data: dict, job_id: str) -> dict:
    """
    Step 03: Speaker ID
    Analyzes diarization output to identify who is the host and who is the guest.
    """
    print(f"[S03] Starting speaker identification for job {job_id}")
    
    try:
        utterances = transcript_data.get("utterances", [])
        
        speaker_stats = {}
        for utterance in utterances:
            speaker = utterance.get("speaker", "UNKNOWN")
            start = utterance.get("start", 0.0)
            end = utterance.get("end", 0.0)
            duration = end - start
            
            if speaker not in speaker_stats:
                speaker_stats[speaker] = {"duration": 0.0, "utterance_count": 0}
            
            speaker_stats[speaker]["duration"] += duration
            speaker_stats[speaker]["utterance_count"] += 1
            
        print(f"[S03] Found {len(speaker_stats)} speakers")
        
        predicted_map = {}
        needs_confirmation = True
        
        if len(speaker_stats) == 1:
            speaker = list(speaker_stats.keys())[0]
            predicted_map[speaker] = {"role": "guest", "name": None}
            needs_confirmation = False
            print(f"[S03] Only one speaker found, assigned as guest")
        elif len(speaker_stats) >= 2:
            # Sort speakers by duration, descending
            sorted_speakers = sorted(speaker_stats.items(), key=lambda x: x[1]["duration"], reverse=True)
            
            # The speaker with MORE duration is guest, LESS duration is host
            # sorted_speakers[0] is the one with the most duration
            guest_speaker = sorted_speakers[0][0]
            predicted_map[guest_speaker] = {"role": "guest", "name": None}
            
            host_speaker = sorted_speakers[1][0]
            predicted_map[host_speaker] = {"role": "host", "name": None}
            
            # For any remaining speakers, assign them as unknown roles
            for i in range(2, len(sorted_speakers)):
                speaker = sorted_speakers[i][0]
                predicted_map[speaker] = {"role": "unknown", "name": None}
                
            print(f"[S03] Heuristic prediction: {guest_speaker} = guest, {host_speaker} = host")
            
        return {
            "speaker_stats": speaker_stats,
            "predicted_map": predicted_map,
            "needs_confirmation": needs_confirmation
        }
        
    except Exception as e:
        print(f"[S03] Error: {e}")
        raise
