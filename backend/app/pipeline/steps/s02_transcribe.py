import re
from typing import Optional
from app.services.deepgram_client import transcribe


def _build_keyterms(channel_dna: dict, video_title: str, guest_name: Optional[str]) -> list[str]:
    """
    Extracts domain-specific terms from channel DNA, video title, and guest name
    for Deepgram Nova-3 keyterm prompting (max 100 terms).
    """
    terms = set()

    # Guest name (highest priority)
    if guest_name and guest_name.strip():
        terms.add(guest_name.strip())
        # Also add individual name parts for better recognition
        for part in guest_name.strip().split():
            if len(part) > 2:
                terms.add(part)

    # Video title words (filter short/common words)
    if video_title:
        for word in video_title.split():
            cleaned = word.strip(".,!?#|()-\"'")
            if len(cleaned) > 3 and cleaned.lower() not in {"with", "from", "this", "that", "what", "when", "about", "episode", "podcast"}:
                terms.add(cleaned)

    # Channel DNA terms
    if channel_dna:
        # Sacred topics
        for topic in channel_dna.get("sacred_topics", []):
            terms.add(topic.strip())
        # No-go zones (still need correct transcription for detection)
        for zone in channel_dna.get("no_go_zones", []):
            terms.add(zone.strip())
        # Best content types
        for ct in channel_dna.get("best_content_types", []):
            terms.add(ct.strip())
        # Custom keyterms field (if channel DNA has it)
        for kt in channel_dna.get("keyterms", []):
            terms.add(kt.strip())

    # Only allow clean alphabetic terms — no special chars, no file extensions, no tech specs
    result = [
        t for t in terms
        if t and len(t) > 1
        and re.fullmatch(r"[A-Za-z][A-Za-z'\-\s]*", t)
    ][:100]
    return result


def run(audio_path: str, job_id: str,
        channel_dna: Optional[dict] = None,
        video_title: Optional[str] = None,
        guest_name: Optional[str] = None) -> dict:
    """
    Step 02: Transcribe
    Calls Deepgram Nova-3 to transcribe the audio file and returns structured data.
    Supports keyterm prompting from channel DNA and video metadata.
    """
    print(f"[S02] Starting transcription for job {job_id}, audio: {audio_path}")

    try:
        # Build keyterms for Nova-3 prompting
        keyterms = _build_keyterms(channel_dna or {}, video_title or "", guest_name)
        if keyterms:
            print(f"[S02] Keyterms for Nova-3: {keyterms[:10]}{'...' if len(keyterms) > 10 else ''}")

        result = transcribe(audio_path, keyterms=keyterms if keyterms else None)

        channels = result.get("results", {}).get("channels", [])
        if not channels:
            raise RuntimeError("Deepgram returned no channels")
        alternative = channels[0].get("alternatives", [{}])[0]
        transcript_text = alternative.get("transcript", "")
        words = alternative.get("words", [])
        utterances = result.get("results", {}).get("utterances", [])
        duration = result.get("metadata", {}).get("duration", 0)

        word_count = len(words)

        # Words array validation — empty words will cause mid-word cuts in S07
        if not words or word_count == 0:
            raise RuntimeError(
                f"Deepgram returned 0 word timestamps for job {job_id}. "
                f"Duration={duration}s, transcript_length={len(transcript_text)}. "
                "Cannot proceed without word-level timestamps for precision cutting."
            )

        print(f"[S02] Transcription completed (Nova-3). Word count: {word_count}, duration: {duration}s")
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
