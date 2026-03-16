import os
from app.config import settings

OUTPUT_DIR = str(settings.OUTPUT_DIR)
UPLOAD_DIR = str(settings.UPLOAD_DIR)

def init_dirs() -> None:
    """Creates OUTPUT_DIR and UPLOAD_DIR if they don't exist."""
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        print(f"[Storage] Initialized directories: {OUTPUT_DIR}, {UPLOAD_DIR}")
    except Exception as e:
        print(f"[Storage] Error initializing directories: {e}")

def save_upload(file_bytes: bytes, filename: str, job_id: str) -> str:
    """Saves uploaded file to UPLOAD_DIR/{job_id}_{filename}."""
    try:
        file_path = os.path.join(UPLOAD_DIR, f"{job_id}_{filename}")
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        print(f"[Storage] Saved upload to {file_path}")
        return file_path
    except Exception as e:
        print(f"[Storage] Error saving upload: {e}")
        return ""

def get_job_output_dir(job_id: str) -> str:
    """Creates OUTPUT_DIR/{job_id}/ if not exists and returns the directory path."""
    try:
        job_dir = os.path.join(OUTPUT_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)
        print(f"[Storage] Created job output directory: {job_dir}")
        return job_dir
    except Exception as e:
        print(f"[Storage] Error getting job output dir: {e}")
        return ""

def cleanup_temp_files(*paths: str) -> None:
    """Deletes each file in paths if it exists, silently ignores missing."""
    try:
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"[Storage] Deleted temp file: {path}")
                except Exception as e:
                    print(f"[Storage] Error deleting {path}: {e}")
    except Exception as e:
        print(f"[Storage] Error in cleanup_temp_files: {e}")

def get_output_url(file_path: str) -> str:
    """Converts local file path like 'output/abc123/clip_01.mp4' to URL path."""
    try:
        normalized_path = file_path.replace("\\", "/")
        if not normalized_path.startswith("/"):
            normalized_path = "/" + normalized_path
        print(f"[Storage] Generated output URL: {normalized_path}")
        return normalized_path
    except Exception as e:
        print(f"[Storage] Error generating output URL: {e}")
        return ""
