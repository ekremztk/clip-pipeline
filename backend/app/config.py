import os
from pathlib import Path

class Settings:
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    GCP_PROJECT: str = os.getenv("GCP_PROJECT", "")
    GCP_LOCATION: str = os.getenv("GCP_LOCATION", "global")
    GCP_CREDENTIALS_JSON: str = os.getenv("GCP_CREDENTIALS_JSON", "")
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "clip-pipeline-audio")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    # Vertex AI model names — override via env var if Vertex releases a new version string
    GEMINI_MODEL_VIDEO: str = os.getenv("GEMINI_MODEL_VIDEO", "gemini-3.1-pro-preview")
    GEMINI_MODEL_PRO: str = os.getenv("GEMINI_MODEL_PRO", "gemini-2.5-pro")
    GEMINI_MODEL_FLASH: str = os.getenv("GEMINI_MODEL_FLASH", "gemini-2.5-flash")
    # Claude
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
    # Separate key with Member role for usage/billing API (usage:read scope)
    # Falls back to DEEPGRAM_API_KEY if not set (will still 403 if key lacks permissions)
    DEEPGRAM_MANAGEMENT_KEY = os.getenv("DEEPGRAM_MANAGEMENT_KEY") or os.getenv("DEEPGRAM_API_KEY")
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

    # Cloudflare WARP proxy (wireproxy SOCKS5 — set WARP_PRIVATE_KEY + WARP_ADDRESS to enable)
    WARP_PRIVATE_KEY: str = os.getenv("WARP_PRIVATE_KEY", "")
    WARP_ADDRESS: str = os.getenv("WARP_ADDRESS", "")

    # Reframe — YOLOv8 model path (pre-downloaded in Docker build)
    YOLOV8_MODEL_PATH: str = os.getenv("YOLOV8_MODEL_PATH", "yolov8n-pose.pt")
    
    # Pipeline constants
    MIN_CLIP_DURATION = 12
    MAX_CLIP_DURATION = 60
    CLIPS_PER_VIDEO = 7
    FFMPEG_CRF = 18
    FFMPEG_PRESET = "slow"

    # Director Module
    RAILWAY_API_TOKEN: str = os.getenv("RAILWAY_API_TOKEN", "")
    RAILWAY_PROJECT_ID: str = os.getenv("RAILWAY_PROJECT_ID", "")
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    POSTHOG_API_KEY: str = os.getenv("POSTHOG_API_KEY", "")
    POSTHOG_HOST: str = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
    # Auto-detect project root: works in both local monorepo and Docker
    # __file__ = .../backend/app/config.py (local) or /app/app/config.py (Docker)
    _backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../backend or /app
    _candidate = os.path.dirname(_backend)  # .../prognot locally, / in Docker
    PROJECT_ROOT: str = _candidate if os.path.isdir(os.path.join(_candidate, "frontend")) else _backend

settings = Settings()
