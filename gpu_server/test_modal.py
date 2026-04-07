"""
Manual test for the Modal reframe worker.

Usage:
    cd /path/to/prognot
    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python gpu_server/test_modal.py

Or export the vars in your shell first, then just:
    python gpu_server/test_modal.py

What it does:
  1. Creates a reframe_jobs row in Supabase with status="pending"
  2. Spawns process_reframe on Modal (non-blocking)
  3. Polls reframe_jobs every 3 s and prints progress until done/error
"""
import os
import sys
import time
import uuid

from supabase import create_client

# ─── Config ───────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY env vars before running.")
    sys.exit(1)

POLL_INTERVAL = 3   # seconds between status checks
POLL_TIMEOUT  = 1800  # stop polling after 30 minutes

# ─── Test payload ─────────────────────────────────────────────────────────────

TEST_CLIP_URL = (
    "https://pub-d053d45c7ff247899fd656863e5d9839.r2.dev/"
    "6baf2442-9063-4e1c-bdbf-284748f5c73f/clip_02_funny_reaction.mp4"
)

# ─── Supabase client ──────────────────────────────────────────────────────────

db = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ─── Step 1: create reframe_jobs row ─────────────────────────────────────────

reframe_job_id = str(uuid.uuid4())

print(f"[test_modal] Creating reframe job: {reframe_job_id}")

db.table("reframe_jobs").insert({
    "id": reframe_job_id,
    "status": "pending",
    "step": "Pending",
    "percent": 0,
    "clip_url": TEST_CLIP_URL,
    "clip_id": None,
    "job_id": "6baf2442-9063-4e1c-bdbf-284748f5c73f",
    "clip_start": 0.0,
    "clip_end": 60.0,
    "strategy": "auto",
    "aspect_ratio": "9:16",
    "tracking_mode": "dynamic_xy",
}).execute()

print(f"[test_modal] Row created.")

# ─── Step 2: spawn Modal function ─────────────────────────────────────────────

payload = {
    "reframe_job_id": reframe_job_id,
    "clip_url": TEST_CLIP_URL,
    "clip_id": None,
    "job_id": "6baf2442-9063-4e1c-bdbf-284748f5c73f",
    "clip_start": 0.0,
    "clip_end": 60.0,
    "strategy": "auto",
    "aspect_ratio": "9:16",
    "tracking_mode": "dynamic_xy",
    "content_type_hint": "interview",
    "detection_engine": "yolo",
    "debug_mode": False,
}

print(f"[test_modal] Spawning Modal function...")

import modal
fn = modal.Function.from_name("prognot-reframe", "process_reframe")
call = fn.spawn(payload)

print(f"[test_modal] Spawned. Modal call ID: {call.object_id}")
print(f"[test_modal] Polling Supabase every {POLL_INTERVAL}s...\n")

# ─── Step 3: poll until done/error ────────────────────────────────────────────

start = time.time()
last_step = None

while True:
    elapsed = time.time() - start
    if elapsed > POLL_TIMEOUT:
        print(f"\n[test_modal] Timed out after {POLL_TIMEOUT}s.")
        break

    resp = db.table("reframe_jobs").select("status,step,percent,error").eq("id", reframe_job_id).execute()

    if not resp.data:
        print("[test_modal] Row not found — something went wrong.")
        break

    row = resp.data[0]
    status  = row.get("status", "")
    step    = row.get("step", "")
    percent = row.get("percent", 0)
    error   = row.get("error")

    # Only print when something changed
    label = f"{step} ({percent}%)"
    if label != last_step:
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] {status:12s}  {percent:3d}%  {step}")
        last_step = label

    if status in ("done", "error"):
        print()
        if status == "done":
            print(f"[test_modal] Done! Check reframe_jobs row {reframe_job_id} for keyframes.")
        else:
            print(f"[test_modal] Failed: {error}")
        break

    time.sleep(POLL_INTERVAL)
