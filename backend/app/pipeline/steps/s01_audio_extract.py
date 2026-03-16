import subprocess
import os

def run(video_path: str, job_id: str) -> str:
    """
    Extracts audio from a video file using FFmpeg.
    Returns the path to the extracted audio file.
    """
    audio_path = f"temp_{job_id}.m4a"
    print(f"[S01] Starting audio extraction from {video_path} to {audio_path}")
    
    command = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vn",
        "-c:a", "aac",
        "-b:a", "128k",
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
            
        print(f"[S01] Successfully extracted audio to {audio_path}")
        return audio_path
        
    except Exception as e:
        print(f"[S01] Error during audio extraction: {e}")
        raise
