def run(
    transcript_data: dict,
    job_id: str,
    video_title: str = "",
    audio_path: str | None = None,
) -> dict:
    """
    Step 03: Speaker ID

    1. Compute speaker stats (total duration, utterance count) from Deepgram utterances.
    2. Assign roles: longest-average-utterance speaker = guest, second = host, rest = unknown.
       (Hosts ask short questions; guests give long answers.)
    3. If audio_path is provided, attempt voice matching via person_voices DB:
       - Extract up to 5 clean 3–9s segments per speaker
       - Embed via Modal ECAPA-TDNN → centroid → pgvector cosine query
       - If similarity ≥ 0.65: assign matched name
       - No match: speaker label stays as SPEAKER_{n}
    4. No LLM fallback — unmatched speakers keep their Deepgram label.
    """
    print(f"[S03] Starting speaker identification for job {job_id}")

    try:
        utterances = transcript_data.get("utterances", [])

        # --- Step 1: compute stats ---
        speaker_stats: dict = {}
        for utt in utterances:
            speaker = str(utt.get("speaker", "UNKNOWN"))
            start = float(utt.get("start", 0.0))
            end = float(utt.get("end", 0.0))
            duration = end - start
            if speaker not in speaker_stats:
                speaker_stats[speaker] = {"duration": 0.0, "utterance_count": 0}
            speaker_stats[speaker]["duration"] += duration
            speaker_stats[speaker]["utterance_count"] += 1

        print(f"[S03] Found {len(speaker_stats)} speakers")

        # --- Step 2: role assignment by heuristic ---
        def avg_utt_duration(stats: dict) -> float:
            count = stats["utterance_count"]
            return stats["duration"] / count if count > 0 else 0.0

        sorted_speakers = sorted(
            speaker_stats.items(),
            key=lambda x: (avg_utt_duration(x[1]), x[1]["duration"]),
            reverse=True,
        )
        for sp_id, stats in sorted_speakers:
            print(
                f"[S03]   Speaker {sp_id}: total={stats['duration']:.1f}s, "
                f"utterances={stats['utterance_count']}, "
                f"avg={avg_utt_duration(stats):.1f}s"
            )

        predicted_map: dict = {}
        if len(sorted_speakers) == 0:
            pass
        elif len(sorted_speakers) == 1:
            predicted_map[sorted_speakers[0][0]] = {"role": "guest", "name": None}
        else:
            predicted_map[sorted_speakers[0][0]] = {"role": "guest", "name": None}
            predicted_map[sorted_speakers[1][0]] = {"role": "host", "name": None}
            for sp_id, _ in sorted_speakers[2:]:
                predicted_map[sp_id] = {"role": "unknown", "name": None}

        # --- Step 3: voice matching ---
        if audio_path and utterances:
            try:
                from app.services.voice_matcher import match_speakers
                matched = match_speakers(utterances, audio_path)
                for speaker_id, name in matched.items():
                    if name and speaker_id in predicted_map:
                        predicted_map[speaker_id]["name"] = name
            except Exception as e:
                print(f"[S03] Voice matching error (non-critical, continuing): {e}")
        else:
            print(f"[S03] Skipping voice matching (audio_path={'missing' if not audio_path else 'ok'}, utterances={len(utterances)})")

        matched_count = sum(1 for v in predicted_map.values() if v.get("name"))
        print(f"[S03] Completed: {len(predicted_map)} speakers, {matched_count} matched by voice")

        return {
            "speaker_stats": speaker_stats,
            "predicted_map": predicted_map,
            "needs_confirmation": False,
        }

    except Exception as e:
        print(f"[S03] Error: {e}")
        raise
