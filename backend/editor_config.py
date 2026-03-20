# EDITOR MODULE — Isolated module, no dependencies on other project files

import os
import logging
from dotenv import load_dotenv

# Set up logging for the editor module
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("editor")

# Load environment variables
load_dotenv()

# Cloudflare R2 configurations
R2_EDITOR_BUCKET_NAME = os.getenv("R2_EDITOR_BUCKET_NAME", "editor-bucket")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")

# GCS configurations
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "editor-gcs-bucket")

# Editor constants
EDITOR_MAX_FILE_SIZE_MB = 500
EDITOR_SUPPORTED_FORMATS = ["mp4", "mov", "webm"]
EDITOR_OUTPUT_DIR = "/tmp/editor_outputs"

# Supabase configurations
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
# Load SUPABASE_SERVICE_KEY
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Celery / Redis
EDITOR_REDIS_URL = os.getenv("EDITOR_REDIS_URL", "redis://localhost:6379/0")

# Deepgram
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

# Ensure output directory exists
os.makedirs(EDITOR_OUTPUT_DIR, exist_ok=True)
