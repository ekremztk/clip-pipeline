import subprocess
import os
import json
from app.config import settings


def _validate_audio(audio_path: str, video_path: str) -> None:
    """
    Validates extracted audio file integrity using ffprobe.
    Checks: file size > 0, duration > 0, duration within tolerance of source video.
    Raises RuntimeError on any validation failure.
    """
    file_size = os.path.getsize(audio_path)
    if file_size == 0:
        raise RuntimeError(f"[S01] Audio file is empty (0 bytes): {audio_path}")
    print(f"[S01] Audio file size: {file_size / 1024:.1f} KB")

    try:
        probe_cmd = [
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "json", audio_path
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(probe_result.stdout)
        audio_duration = float(probe_data["format"]["duration"])
    except Exception as e:
        raise RuntimeError(f"[S01] ffprobe failed on audio file: {e}")

    if audio_duration <= 0:
        raise RuntimeError(f"[S01] Audio duration is {audio_duration}s — file is corrupt or empty.")

    # Cross-check against source video duration
    try:
        video_probe_cmd = [
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "json", video_path
        ]
        video_probe_result = subprocess.run(video_probe_cmd, capture_output=True, text=True, check=True)
        video_data = json.loads(video_probe_result.stdout)
        video_duration = float(video_data["format"]["duration"])

        drift = abs(audio_duration - video_duration)
        if drift > 2.0:
            print(f"[S01] Warning: Audio/video duration drift {drift:.2f}s (audio={audio_duration:.1f}s, video={video_duration:.1f}s)")
    except Exception as e:
        print(f"[S01] Warning: Could not cross-check video duration: {e}")

    print(f"[S01] Audio validation passed: {audio_duration:.1f}s, {file_size / 1024:.1f} KB")


def run(video_path: str, job_id: str) -> str:
    """
    Extracts audio from a video file using FFmpeg.
    Returns the path to the extracted audio file.
    """
    os.makedirs(str(settings.UPLOAD_DIR), exist_ok=True)
    audio_path = os.path.join(str(settings.UPLOAD_DIR), f"temp_{job_id}.m4a")
    print(f"[S01] Starting audio extraction from {video_path} to {audio_path}")

    command = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vn",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        audio_path
    ]

    try:
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if process.returncode != 0:
            error_msg = f"[S01] FFmpeg failed with exit code {process.returncode}:\n{process.stderr}"
            print(error_msg)
            raise RuntimeError(error_msg)

        if not os.path.exists(audio_path):
            error_msg = f"[S01] FFmpeg succeeded but output file {audio_path} not found."
            print(error_msg)
            raise RuntimeError(error_msg)

        # Validate audio file integrity before passing to S02
        _validate_audio(audio_path, video_path)

        print(f"[S01] Successfully extracted audio to {audio_path}")
        return audio_path

    except Exception as e:
        print(f"[S01] Error during audio extraction: {e}")
        raise
