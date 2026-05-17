from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

from app.pipeline.steps import s01_audio_extract
from app.services.deepgram_client import transcribe


def _probe_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout or "{}")
    return float((data.get("format") or {}).get("duration") or 0)


def _detect_silence(audio_path: str) -> list[dict[str, Any]]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        audio_path,
        "-af",
        "silencedetect=noise=-35dB:d=0.25",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    text = result.stderr or ""

    gaps: list[dict[str, Any]] = []
    current_start: float | None = None
    for line in text.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            current_start = float(start_match.group(1))
            continue

        end_match = re.search(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", line)
        if end_match and current_start is not None:
            end = float(end_match.group(1))
            duration = float(end_match.group(2))
            gaps.append(
                {
                    "start_s": round(current_start, 3),
                    "end_s": round(end, 3),
                    "duration_s": round(duration, 3),
                }
            )
            current_start = None

    return gaps


def _extract_words(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    channels = ((transcript.get("results") or {}).get("channels") or [])
    if not channels:
        return []
    alternatives = channels[0].get("alternatives") or []
    if not alternatives:
        return []
    return alternatives[0].get("words") or []


def _extract_transcript_text(transcript: dict[str, Any]) -> str:
    channels = ((transcript.get("results") or {}).get("channels") or [])
    if not channels:
        return ""
    alternatives = channels[0].get("alternatives") or []
    if not alternatives:
        return ""
    return alternatives[0].get("transcript") or ""


def run(video_path: str, work_id: str) -> dict[str, Any]:
    """Extract audio, run Nova-3, and detect silence gaps."""
    audio_path = ""
    try:
        audio_path = s01_audio_extract.run(video_path, f"provision_{work_id}")
        transcript = transcribe(audio_path, keyterms=None)
        duration_s = _probe_duration(video_path)
        silence_gaps = _detect_silence(audio_path)
        words = _extract_words(transcript)
        transcript_text = _extract_transcript_text(transcript)

        return {
            "audio_path": audio_path,
            "nova_transcript": transcript,
            "audio_analysis": {
                "duration_s": round(duration_s, 3),
                "silence_gaps": silence_gaps,
                "word_count": len(words),
                "transcript_preview": transcript_text[:1000],
            },
            "words": words,
            "transcript_text": transcript_text,
        }
    except Exception as exc:
        print(f"[Provision/P02] Error: {exc}")
        raise
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass

