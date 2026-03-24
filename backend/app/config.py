import os
from pathlib import Path

class Settings:
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    GCP_PROJECT: str = os.getenv("GCP_PROJECT", "")
    GCP_LOCATION: str = os.getenv("GCP_LOCATION", "global")
    GCP_CREDENTIALS_JSON: str = os.getenv("GCP_CREDENTIALS_JSON", "")
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "clip-pipeline-audio")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL_PRO: str = "gemini-3.1-pro-preview"
    GEMINI_MODEL_FLASH: str = "gemini-2.5-flash"
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL")
    FRONTEND_URL = os.getenv("FRONTEND_URL")
    
    # Cloudflare R2
    R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
    R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
    R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
    R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
    R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")
    
    # Path variables
    OUTPUT_DIR = Path("output")
    UPLOAD_DIR = Path("temp_uploads")
    
    # Pipeline constants
    MIN_CLIP_DURATION = 12
    MAX_CLIP_DURATION = 60
    CLIPS_PER_VIDEO = 7
    FFMPEG_CRF = 18
    FFMPEG_PRESET = "slow"

    # Director Module
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    POSTHOG_API_KEY: str = os.getenv("POSTHOG_API_KEY", "")
    POSTHOG_HOST: str = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
    PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

settings = Settings()
