def _extract_guest_name_from_title(video_title: str) -> str | None:
    """
    Uses Gemini Flash to extract a guest name from the video title.
    Returns the guest name string or None if not found.
    """
    try:
        from app.services.gemini_client import call_gemini
        from app.config import settings

        prompt = (
            "Extract the guest's name from this podcast/video title if one exists. "
            "Return ONLY the name (first and last name if available), nothing else. "
            "If no guest name is present, return the word NULL.\n\n"
            "Title: " + video_title
        )
        result = call_gemini(prompt, model=settings.GEMINI_MODEL_FLASH)
        result = result.strip()
        if result and result.upper() != "NULL" and len(result) < 60:
            return result
        return None
    except Exception as e:
        print(f"[S03] Guest name extraction error (non-critical): {e}")
        return None


def run(transcript_data: dict, job_id: str, video_title: str = "") -> dict:
    """
    Step 03: Speaker ID
    Analyzes diarization output to identify speakers.
    Tries to extract a guest name from the video title automatically.
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

        # Try to extract guest name from video title
        guest_name = None
        if video_title:
            guest_name = _extract_guest_name_from_title(video_title)
            if guest_name:
                print(f"[S03] Extracted guest name from title: {guest_name}")

        predicted_map = {}

        if len(speaker_stats) == 1:
            speaker = list(speaker_stats.keys())[0]
            predicted_map[speaker] = {"role": "guest", "name": guest_name}
            print(f"[S03] Only one speaker found, assigned as guest")
        elif len(speaker_stats) >= 2:
            # Sort speakers by duration, descending
            # Speaker with MORE total duration is assumed to be the guest
            sorted_speakers = sorted(speaker_stats.items(), key=lambda x: x[1]["duration"], reverse=True)

            guest_speaker = sorted_speakers[0][0]
            predicted_map[guest_speaker] = {"role": "guest", "name": guest_name}

            host_speaker = sorted_speakers[1][0]
            predicted_map[host_speaker] = {"role": "host", "name": None}

            for i in range(2, len(sorted_speakers)):
                speaker = sorted_speakers[i][0]
                predicted_map[speaker] = {"role": "unknown", "name": None}

            print(f"[S03] Heuristic: {guest_speaker} = guest, {host_speaker} = host")

        return {
            "speaker_stats": speaker_stats,
            "predicted_map": predicted_map,
            "needs_confirmation": False
        }

    except Exception as e:
        print(f"[S03] Error: {e}")
        raise
