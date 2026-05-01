def run(
    transcript_data: dict,
    speaker_map: dict,
    target_guest: str | None = None,
    scene_ranges: list[tuple[float, float]] | None = None,
) -> str:
    """
    s04: Merges transcript data with speaker map to create a labeled transcript.

    Args:
        transcript_data: dict from s02 containing 'words' or 'utterances' with text and timestamps
        speaker_map: dict mapping speaker IDs to roles and names.
            Keys can be raw integers (0, 1) from S03 or strings ("SPEAKER_0").
        target_guest: optional string to use for guest speaker label
        scene_ranges: optional list of (start, end) tuples (episode seconds). When
            provided, only utterances inside one of the ranges are emitted and
            each range is prefixed with a `[Scene N — MM:SS to MM:SS]` header so
            S05 can see where the gaps are. Timestamps remain absolute.

    Returns:
        Full labeled transcript as a single string
    """
    try:
        if not transcript_data:
            raise RuntimeError("transcript_data is empty")

        utterances = transcript_data.get("utterances", [])
        if not utterances:
            raise RuntimeError("No utterances found in transcript_data")

        def _fmt_ts(sec: float) -> str:
            m = int(sec // 60)
            s = sec % 60
            return f"{m:02d}:{s:05.2f}"

        def _scene_for(start_sec: float) -> int | None:
            if not scene_ranges:
                return None
            for idx, (s, e) in enumerate(scene_ranges):
                if s <= start_sec < e:
                    return idx
            return None

        labeled_lines: list[str] = []
        current_scene: int | None = None
        count = 0

        for utt in utterances:
            text = utt.get("transcript", "").strip()
            if not text:
                continue

            start_sec = float(utt.get("start", 0.0))

            # Scene filter: skip if filter active and utterance is outside all scenes
            if scene_ranges is not None:
                scene_idx = _scene_for(start_sec)
                if scene_idx is None:
                    continue
                if scene_idx != current_scene:
                    s, e = scene_ranges[scene_idx]
                    labeled_lines.append(
                        f"\n[Scene {scene_idx + 1} — {_fmt_ts(s)} to {_fmt_ts(e)}]"
                    )
                    current_scene = scene_idx

            raw_speaker = utt.get("speaker", "")
            speaker_info = (
                speaker_map.get(raw_speaker)
                or speaker_map.get(str(raw_speaker))
                or speaker_map.get(f"SPEAKER_{raw_speaker}")
                or {}
            )
            role = speaker_info.get("role", "UNKNOWN").upper()
            name = speaker_info.get("name", "")

            if role == "GUEST" and target_guest:
                name = target_guest

            speaker_label = f"{role} ({name})" if name else role

            minutes = int(start_sec // 60)
            seconds = start_sec % 60
            timestamp = f"[{minutes:02d}:{seconds:05.2f}]"

            sentiment_str = ""
            raw_sentiment = utt.get("sentiment_score") or utt.get("sentiment")
            if raw_sentiment is not None:
                try:
                    score = float(raw_sentiment)
                    if abs(score) > 0.3:
                        sentiment_str = f" [sentiment:{score:.2f}]"
                except (ValueError, TypeError):
                    pass

            line = f"{timestamp} {speaker_label}:{sentiment_str} {text}"
            labeled_lines.append(line)
            count += 1

        result_str = "\n".join(labeled_lines).lstrip("\n")
        if scene_ranges is not None:
            print(
                f"[S04] Scene-filtered transcript: {count} utterances across "
                f"{len(scene_ranges)} scene(s)"
            )
        else:
            print(f"[S04] Generated labeled transcript with {count} utterances")
        return result_str

    except RuntimeError as re:
        raise re
    except Exception as e:
        print(f"[S04] Error: {e}")
        raise RuntimeError(f"Failed to generate labeled transcript: {e}")
