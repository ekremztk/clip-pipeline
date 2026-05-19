"""
Voice matching service for S03 speaker identification.

For each Deepgram diarization cluster, extracts up to 5 clean audio segments
(3–9 seconds, confidence ≥ 0.70), computes ECAPA-TDNN embeddings via Modal,
averages them into a centroid, then queries person_voices via pgvector cosine
similarity. Returns a mapping of speaker_id → matched name (or None).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Optional

from app.config import settings

SEGMENT_MIN_SEC = 3.0
SEGMENT_MAX_SEC = 9.0
CONFIDENCE_THRESHOLD = 0.70
MAX_SEGMENTS_PER_SPEAKER = 5
MATCH_THRESHOLD = 0.65


def _cut_segment(audio_path: str, start: float, end: float) -> Optional[bytes]:
    """Cut [start, end] from audio_path → 16kHz mono WAV bytes. Returns None on error."""
    duration = end - start
    if duration < SEGMENT_MIN_SEC or duration > SEGMENT_MAX_SEC:
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", audio_path,
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            tmp_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            return None
        with open(tmp_path, "rb") as f:
            return f.read()
    except Exception as e:
        print(f"[VoiceMatcher] segment cut error: {e}")
        return None
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def _embed_via_modal(audio_bytes: bytes, filename: str = "segment.wav") -> Optional[list[float]]:
    """Call Modal compute_voice_embedding. Returns 192-dim list or None on failure."""
    try:
        import modal
        fn = modal.Function.from_name(settings.MODAL_GPU_APP_NAME, settings.MODAL_GPU_VOICE_FUNCTION_NAME)
        result = fn.remote(audio_bytes, filename)
        if not isinstance(result, dict) or "error" in result:
            return None
        embedding = result.get("embedding")
        if not embedding or len(embedding) != 192:
            return None
        return embedding
    except Exception as e:
        print(f"[VoiceMatcher] Modal embed error: {e}")
        return None


def _centroid(vectors: list[list[float]]) -> list[float]:
    """Average a list of equal-length vectors into a centroid."""
    dim = len(vectors[0])
    result = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            result[i] += x
    n = len(vectors)
    return [x / n for x in result]


def _query_db(embedding: list[float], threshold: float = MATCH_THRESHOLD) -> Optional[tuple[str, str, float]]:
    """Query person_voices via match_voice RPC. Returns (name, role, similarity) or None."""
    try:
        from app.services.supabase_client import get_client
        sb = get_client()
        res = sb.rpc("match_voice", {
            "query_embedding": embedding,
            "match_threshold": threshold,
            "match_count": 1,
        }).execute()
        if res.data:
            row = res.data[0]
            return row["name"], row.get("role", "guest"), float(row["similarity"])
        return None
    except Exception as e:
        print(f"[VoiceMatcher] DB query error: {e}")
        return None


def match_speakers(
    utterances: list[dict],
    audio_path: str,
    threshold: float = MATCH_THRESHOLD,
) -> dict[str, Optional[dict]]:
    """
    Main entry point. Given Deepgram utterances and the local audio file,
    returns {speaker_id: matched_name_or_None} for every unique speaker.

    Utterance schema (Deepgram):
      {"speaker": 0, "start": 1.23, "end": 5.67, "transcript": "...", "confidence": 0.95}

    Only utterances with:
      - duration 3–9 seconds
      - confidence ≥ 0.70
    are used for embedding. Up to MAX_SEGMENTS_PER_SPEAKER per speaker.
    Multiple embeddings are averaged (centroid) before DB lookup.

    Returns {speaker_id: {"name": str, "role": str} or None}
    """
    # Group utterances by speaker
    by_speaker: dict = {}
    for utt in utterances:
        sid = str(utt.get("speaker", ""))
        if sid not in by_speaker:
            by_speaker[sid] = []
        by_speaker[sid].append(utt)

    results: dict[str, Optional[dict]] = {}

    for speaker_id, utts in by_speaker.items():
        # Filter by confidence and duration, sort longest first
        candidates = []
        for utt in utts:
            start = float(utt.get("start", 0))
            end = float(utt.get("end", 0))
            duration = end - start
            confidence = float(utt.get("confidence") or 1.0)
            if (SEGMENT_MIN_SEC <= duration <= SEGMENT_MAX_SEC
                    and confidence >= CONFIDENCE_THRESHOLD):
                candidates.append((utt, duration))

        # Sort longest first for best signal quality
        candidates.sort(key=lambda x: x[1], reverse=True)
        candidates = candidates[:MAX_SEGMENTS_PER_SPEAKER]

        if not candidates:
            print(f"[VoiceMatcher] Speaker {speaker_id}: no qualifying segments, skipping")
            results[speaker_id] = None
            continue

        embeddings = []
        for utt, dur in candidates:
            audio_bytes = _cut_segment(audio_path, utt["start"], utt["end"])
            if audio_bytes is None:
                continue
            vec = _embed_via_modal(audio_bytes)
            if vec is not None:
                embeddings.append(vec)

        if not embeddings:
            print(f"[VoiceMatcher] Speaker {speaker_id}: all segments failed embedding")
            results[speaker_id] = None
            continue

        centroid = _centroid(embeddings) if len(embeddings) > 1 else embeddings[0]
        match = _query_db(centroid, threshold)

        if match:
            name, role, similarity = match
            print(f"[VoiceMatcher] Speaker {speaker_id} → '{name}' ({role}, similarity={similarity:.3f}, segments={len(embeddings)})")
            results[speaker_id] = {"name": name, "role": role}
        else:
            print(f"[VoiceMatcher] Speaker {speaker_id}: no match above threshold={threshold}")
            results[speaker_id] = None

    return results
