import os
from pathlib import Path

class Settings:
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = "gemini-2.5-pro-preview-05-06"
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
