import os
from pathlib import Path

class Settings:
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    GCP_PROJECT: str = os.getenv("GCP_PROJECT", "")
    GCP_LOCATION: str = os.getenv("GCP_LOCATION", "us-central1")
    GCP_CREDENTIALS_JSON: str = os.getenv("GCP_CREDENTIALS_JSON", "")
    GEMINI_MODEL_PRO: str = "gemini-2.5-pro"
    GEMINI_MODEL_FLASH: str = "gemini-2.5-flash"
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL")
    FRONTEND_URL = os.getenv("FRONTEND_URL")
    
    # Path variables
    OUTPUT_DIR = Path("output")
    UPLOAD_DIR = Path("temp_uploads")
    
    # Pipeline constants
    MIN_CLIP_DURATION = 15
    MAX_CLIP_DURATION = 50
    CLIPS_PER_VIDEO = 7
    FFMPEG_CRF = 18
    FFMPEG_PRESET = "slow"

settings = Settings()
