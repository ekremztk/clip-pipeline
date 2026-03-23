"""
Fetches speaker diarization data from Supabase.
Maps Deepgram utterances to clip timestamps to produce speaker segments.
"""

from typing import List, Optional
from app.services.supabase_client import get_client


def get_speaker_segments(
    job_id: str,
    clip_start: float,
    clip_end: float,
) -> List[dict]:
    """
    Fetches utterance-level diarization for a job and filters/adjusts
    timestamps to be relative to the clip's start time.

    Returns list of:
    {
        "speaker": int,          # 0 or 1
        "start": float,          # seconds, relative to clip start
        "end": float,            # seconds, relative to clip start
    }
    Sorted by start time.
    """
    try:
        supabase = get_client()
        resp = supabase.table("transcripts").select(
            "word_timestamps, speaker_map"
        ).eq("job_id", job_id).execute()

        if not resp.data:
            print(f"[Diarization] No transcript found for job {job_id}")
            return []

        row = resp.data[0]
        words = row.get("word_timestamps") or []
        speaker_map = row.get("speaker_map") or {}

        if not words:
            return []

        # Build utterance segments from word-level timestamps
        # Words have: {"word": str, "start": float, "end": float, "speaker": int}
        segments = _build_segments_from_words(words, speaker_map)

        # Filter to clip window and adjust to clip-relative timestamps
        clip_segments = []
        for seg in segments:
            # Skip segments completely outside clip
            if seg["end"] <= clip_start or seg["start"] >= clip_end:
                continue

            clipped_start = max(0.0, seg["start"] - clip_start)
            clipped_end = min(clip_end - clip_start, seg["end"] - clip_start)

            if clipped_end <= clipped_start:
                continue

            clip_segments.append({
                "speaker": seg["speaker"],
                "start": round(clipped_start, 3),
                "end": round(clipped_end, 3),
            })

        print(f"[Diarization] {len(clip_segments)} segments in clip [{clip_start:.1f}–{clip_end:.1f}s]")
        return clip_segments

    except Exception as e:
        print(f"[Diarization] Error fetching segments: {e}")
        return []


def get_active_speaker(segments: List[dict], time_s: float) -> Optional[int]:
    """
    Returns the speaker index active at the given timestamp, or None if silence.
    Uses last-active fallback: returns the last speaker if we're in a gap.
    """
    try:
        last_speaker = None
        for seg in segments:
            if seg["start"] <= time_s <= seg["end"]:
                return seg["speaker"]
            if seg["start"] <= time_s:
                last_speaker = seg["speaker"]

        return last_speaker

    except Exception as e:
        print(f"[Diarization] get_active_speaker error: {e}")
        return None


def _build_segments_from_words(words: list, speaker_map: dict) -> List[dict]:
    """
    Groups consecutive words by speaker into segments.
    speaker_map maps Deepgram speaker IDs to role labels ("HOST", "GUEST").
    We map HOST → speaker index 0, GUEST → speaker index 1.
    """
    try:
        # Build role → numeric index mapping
        # speaker_map looks like: {"0": "HOST", "1": "GUEST"} or {"HOST": "0", "GUEST": "1"}
        raw_to_index = {}
        for k, v in speaker_map.items():
            role = str(v).upper()
            raw_id = str(k)
            if role == "HOST":
                raw_to_index[raw_id] = 0
            elif role == "GUEST":
                raw_to_index[raw_id] = 1

        segments = []
        current_speaker = None
        current_start = None
        current_end = None

        for word in words:
            raw_speaker = str(word.get("speaker", 0))
            # Map to 0 or 1; if not in map, use raw number
            speaker_idx = raw_to_index.get(raw_speaker, int(raw_speaker) % 2)

            w_start = float(word.get("start", 0))
            w_end = float(word.get("end", 0))

            if speaker_idx != current_speaker:
                # Flush current segment
                if current_speaker is not None and current_start is not None:
                    segments.append({
                        "speaker": current_speaker,
                        "start": current_start,
                        "end": current_end,
                    })
                current_speaker = speaker_idx
                current_start = w_start
                current_end = w_end
            else:
                current_end = w_end

        # Flush last segment
        if current_speaker is not None and current_start is not None:
            segments.append({
                "speaker": current_speaker,
                "start": current_start,
                "end": current_end,
            })

        return segments

    except Exception as e:
        print(f"[Diarization] _build_segments_from_words error: {e}")
        return []
