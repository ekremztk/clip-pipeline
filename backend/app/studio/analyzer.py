import json
import os
import subprocess
import tempfile

from app.services.deepgram_client import transcribe
from app.services.gemini_client import analyze_video
from app.studio.prompt import STUDIO_ANALYZE_SYSTEM, build_analyze_prompt
from app.config import settings


def _extract_audio(video_path: str) -> str:
    audio_path = tempfile.mktemp(suffix=".m4a", prefix="studio_audio_")
    command = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        audio_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"[Studio] FFmpeg audio extract failed: {result.stderr[:500]}")
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        raise RuntimeError("[Studio] FFmpeg produced empty audio file")
    return audio_path


def _format_transcript_with_timestamps(words: list[dict]) -> str:
    lines = []
    current_line = []
    line_start = None

    for w in words:
        word_text = w.get("word", w.get("punctuated_word", ""))
        start = w.get("start", 0)
        end = w.get("end", 0)

        if line_start is None:
            line_start = start

        current_line.append(word_text)

        if len(current_line) >= 12 or word_text.endswith((".", "!", "?")):
            lines.append(f"[{line_start:.2f}s - {end:.2f}s] {' '.join(current_line)}")
            current_line = []
            line_start = None

    if current_line:
        last_end = words[-1].get("end", 0) if words else 0
        lines.append(f"[{line_start:.2f}s - {last_end:.2f}s] {' '.join(current_line)}")

    return "\n".join(lines)


def _get_video_duration(video_path: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def analyze_clip(video_path: str) -> dict:
    audio_path = None
    try:
        print(f"[Studio] Starting analysis for: {video_path}")

        duration = _get_video_duration(video_path)
        print(f"[Studio] Video duration: {duration:.1f}s")

        audio_path = _extract_audio(video_path)
        print(f"[Studio] Audio extracted: {audio_path}")

        transcript_result = transcribe(audio_path)
        channels = transcript_result.get("results", {}).get("channels", [])
        if not channels:
            raise RuntimeError("[Studio] Deepgram returned no channels")

        words = channels[0].get("alternatives", [{}])[0].get("words", [])
        if not words:
            raise RuntimeError("[Studio] Deepgram returned no word timestamps")

        print(f"[Studio] Transcript: {len(words)} words")

        formatted_transcript = _format_transcript_with_timestamps(words)
        prompt = build_analyze_prompt(formatted_transcript, duration)

        print(f"[Studio] Sending to Gemini (video + transcript)...")
        raw_response = analyze_video(
            video_path=video_path,
            prompt=f"{STUDIO_ANALYZE_SYSTEM}\n\n{prompt}",
            model=settings.GEMINI_MODEL_PRO,
            json_mode=True,
        )

        result = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
        result["total_duration_seconds"] = duration
        result["word_count"] = len(words)

        print(f"[Studio] Analysis complete. Segments: {len(result.get('segments', []))}")
        return result

    except json.JSONDecodeError as e:
        print(f"[Studio] JSON parse error: {e}")
        raise RuntimeError(f"Gemini returned invalid JSON: {e}")
    except Exception as e:
        print(f"[Studio] Error: {e}")
        raise
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
