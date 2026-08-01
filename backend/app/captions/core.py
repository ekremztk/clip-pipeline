"""
Caption core — shared transcription + word segmentation logic.

Used by:
  - /captions/generate (editor API)
  - s10_captions (pipeline step)
"""
import os
import subprocess
import time
from typing import Optional

import httpx

from app.config import settings

# Deepgram uploads occasionally stall mid-request: the socket goes quiet and the
# write phase blocks until it hits its ceiling. A single failure used to leave
# the clip permanently uncaptioned, so retry the transient cases.
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = (2, 8)

# One scalar timeout applies to all four phases at once, which meant a dead
# connection was waited on for the full read budget. Split them so a stalled
# upload fails fast enough to leave room for a retry.
_DEEPGRAM_TIMEOUT = httpx.Timeout(connect=10.0, write=60.0, read=180.0, pool=10.0)


def convert_to_wav(input_path: str, output_path: str) -> None:
    """Convert any audio/video file to mono 16kHz WAV for Deepgram."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        output_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg WAV conversion failed: {result.stderr.decode()[:300]}")


def transcribe_with_deepgram(wav_path: str, language: Optional[str] = None) -> dict:
    """Send WAV file to Deepgram nova-3 and return raw JSON response."""
    with open(wav_path, "rb") as f:
        audio_data = f.read()

    headers = {
        "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
        "Content-Type": "audio/wav",
    }

    params = {
        # Matches S02 (services/deepgram_client.py). This call re-transcribes the
        # already-cut clip to re-align word timings against the rendered audio, but
        # the words it returns are what gets burned into the video — on nova-2 they
        # could come back worse than the nova-3 transcript the pipeline already had.
        "model": "nova-3",
        "punctuate": "true",
        "words": "true",
        "smart_format": "true",
    }

    if language and language != "auto":
        params["language"] = language
    else:
        params["detect_language"] = "true"

    last_error: Exception | None = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = httpx.post(
                "https://api.deepgram.com/v1/listen",
                headers=headers,
                params=params,
                content=audio_data,
                timeout=_DEEPGRAM_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()

        except httpx.TransportError as e:
            # Timeout, stalled connection, or dropped socket — worth another try.
            last_error = e
        except httpx.HTTPStatusError as e:
            # 4xx means a bad key or a malformed request; retrying cannot help.
            if e.response.status_code < 500:
                raise
            last_error = e

        if attempt < _MAX_ATTEMPTS - 1:
            delay = _RETRY_BACKOFF_SECONDS[attempt]
            print(
                f"[Captions] Deepgram attempt {attempt + 1}/{_MAX_ATTEMPTS} failed "
                f"({type(last_error).__name__}); retrying in {delay}s"
            )
            time.sleep(delay)

    raise RuntimeError(
        f"Deepgram transcription failed after {_MAX_ATTEMPTS} attempts: {last_error}"
    ) from last_error


def build_word_list(words: list) -> list[dict]:
    """Normalize Deepgram word objects into a consistent word list."""
    return [
        {
            "word": w.get("word", ""),
            "punctuated_word": w.get("punctuated_word") or w.get("word", ""),
            "start": w.get("start", 0),
            "end": w.get("end", 0),
            "confidence": w.get("confidence", 1.0),
        }
        for w in words
    ]


def build_segments_from_words(words: list, max_words: int = 10) -> list[dict]:
    """
    Group word-level results into sentence-like segments.
    Splits on sentence-ending punctuation or every max_words words.
    """
    segments = []
    current_words = []
    current_start = None

    for w in words:
        word_text = w.get("punctuated_word") or w.get("word", "")
        word_start = w.get("start", 0)
        word_end = w.get("end", 0)

        if current_start is None:
            current_start = word_start

        current_words.append(word_text)
        ends_sentence = word_text.rstrip().endswith((".", "?", "!"))
        too_long = len(current_words) >= max_words

        if ends_sentence or too_long:
            segments.append({
                "text": " ".join(current_words),
                "start": current_start,
                "end": word_end,
            })
            current_words = []
            current_start = None

    if current_words and current_start is not None:
        last_end = words[-1].get("end", current_start + 1) if words else current_start + 1
        segments.append({
            "text": " ".join(current_words),
            "start": current_start,
            "end": last_end,
        })

    return segments


def transcribe_video(
    video_path: str,
    language: Optional[str] = None,
) -> dict:
    """
    Full transcription pipeline for a local video file.

    1. FFmpeg: extract mono 16kHz WAV
    2. Deepgram nova-3: transcribe with word timestamps
    3. Build word list + segments

    Returns:
        {
            "words": [...],       # word-level timestamps
            "segments": [...],    # grouped sentence segments
            "text": "...",        # full transcript
            "language": "...",    # detected or requested language
        }
    """
    wav_path = video_path + "_captions_16k.wav"
    try:
        convert_to_wav(video_path, wav_path)
        raw = transcribe_with_deepgram(wav_path, language)
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass

    channels = raw.get("results", {}).get("channels", [])
    if not channels:
        raise RuntimeError("Deepgram returned no channels in response")

    alternative = channels[0].get("alternatives", [{}])[0]
    raw_words = alternative.get("words", [])
    transcript = alternative.get("transcript", "")

    detected_language = (
        channels[0].get("detected_language")
        or (language if language and language != "auto" else "auto")
    )

    word_list = build_word_list(raw_words)
    segments = build_segments_from_words(raw_words)

    return {
        "words": word_list,
        "segments": segments,
        "text": transcript,
        "language": detected_language,
    }
