#!/usr/bin/env bash
# ── Prognot GPU Reframe Server — startup script ───────────────────────────────
# Usage: bash gpu_server/start.sh
# Run from repo root OR from within gpu_server/ — both work.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"

# ── Load .env from backend if present (local dev / first-time EC2 setup) ─────
ENV_FILE="$BACKEND_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo "[start.sh] Loading env from $ENV_FILE"
    set -o allexport
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +o allexport
fi

# ── Temp upload directory ─────────────────────────────────────────────────────
# The pipeline downloads videos here before processing. Separate from Railway's
# temp_uploads so both services can run from the same repo without conflicts.
export UPLOAD_DIR="${UPLOAD_DIR:-/tmp/reframe_uploads}"
mkdir -p "$UPLOAD_DIR"
echo "[start.sh] UPLOAD_DIR=$UPLOAD_DIR"

# ── Validate required env vars ────────────────────────────────────────────────
REQUIRED_VARS=(SUPABASE_URL SUPABASE_SERVICE_KEY GEMINI_API_KEY GCP_PROJECT GCP_CREDENTIALS_JSON)
MISSING=()
for VAR in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!VAR:-}" ]; then
        MISSING+=("$VAR")
    fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "[start.sh] ERROR: Missing required env vars: ${MISSING[*]}"
    exit 1
fi

# ── CUDA sanity check ─────────────────────────────────────────────────────────
echo "[start.sh] PyTorch CUDA availability:"
python3 -c "import torch; print(f'  torch={torch.__version__}  cuda={torch.cuda.is_available()}  device_count={torch.cuda.device_count()}')" 2>/dev/null \
    || echo "  torch not found — YOLOv8 will run on CPU"

# ── Launch uvicorn ────────────────────────────────────────────────────────────
# Single worker: GPU is a shared resource; multi-worker would compete for VRAM.
# The daemon-thread-per-job model handles concurrency inside the single process.
echo "[start.sh] Starting GPU reframe server on :8081"
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8081 \
    --workers 1 \
    --app-dir "$SCRIPT_DIR" \
    --log-level info
