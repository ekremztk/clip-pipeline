"""Helpers for matching DaVinci-style MP4 container timing."""
import json
import subprocess
from fractions import Fraction


def probe_video_rate(path: str) -> Fraction:
    """Return the source video frame rate as a Fraction."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate,avg_frame_rate",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe frame-rate probe failed: {result.stderr[-400:]}")

    data = json.loads(result.stdout or "{}")
    stream = (data.get("streams") or [{}])[0]
    for key in ("r_frame_rate", "avg_frame_rate"):
        value = stream.get(key)
        if value and value != "0/0":
            try:
                return Fraction(value)
            except Exception:
                continue
    return Fraction(30, 1)


def has_audio_stream(path: str) -> bool:
    """Return True if the file has at least one audio stream."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def davinci_timescale_for_rate(rate: Fraction) -> int:
    """Return the movie/video track timescale DaVinci commonly writes."""
    fps = float(rate)
    if abs(fps - 25.0) < 0.01:
        return 12800
    if rate.denominator != 1:
        return int(rate.numerator)
    if abs(fps - round(fps)) < 0.01:
        return int(round(fps)) * 1000
    return max(1000, int(round(fps * 1000)))


def frame_duration_s(rate: Fraction) -> float:
    """Return one frame duration in seconds."""
    if rate.numerator <= 0:
        return 1.0 / 30.0
    return float(rate.denominator / rate.numerator)
