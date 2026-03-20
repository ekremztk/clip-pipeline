# EDITOR MODULE — Isolated module, no dependencies on other project files

"""
CREATE TABLE editor_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  user_id UUID REFERENCES auth.users(id),   -- For Row Level Security
  status TEXT DEFAULT 'pending',             -- pending | processing | completed | failed
  progress INTEGER DEFAULT 0,               -- 0-100
  source_r2_key TEXT,                        -- source video key in R2
  output_r2_key TEXT,                        -- output video key in R2
  transcript JSONB,                          -- Deepgram response (words + speaker info)
  speaker_segments JSONB,                    -- [{start, end, speaker_id, face_x}]
  silence_map JSONB,                         -- Librosa silence analysis
  video_metadata JSONB,                      -- {duration, fps, width, height}
  crop_segments JSONB,                       -- [{"start", "end", "speaker_id", "crop_x", "crop_x_pixels", "detected", "confidence"}]
  edit_spec JSONB,                           -- edit instructions sent from frontend
  error_message TEXT
);
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from supabase import create_client, Client
from editor_config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger("editor.database")

def get_client() -> Client:
    """Initialize and return Supabase client."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Missing Supabase configuration")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

async def create_editor_job(user_id: str) -> str:
    """
    Creates a new editor job for the given user.
    """
    try:
        supabase = get_client()
        # Since supabase-py standard client is synchronous, we use asyncio.to_thread to run it without blocking
        response = await asyncio.to_thread(
            lambda: supabase.table("editor_jobs").insert({"user_id": user_id}).execute()
        )
        if not response.data:
            raise RuntimeError("Failed to create job, no data returned")
        return response.data[0]["id"]
    except Exception as e:
        logger.error(f"Error creating editor job for user {user_id}: {e}")
        raise RuntimeError(f"Database error: {e}") from e

async def get_editor_job(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves an editor job by its ID.
    """
    try:
        supabase = get_client()
        response = await asyncio.to_thread(
            lambda: supabase.table("editor_jobs").select("*").eq("id", job_id).execute()
        )
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error retrieving editor job {job_id}: {e}")
        raise RuntimeError(f"Database error: {e}") from e

async def update_editor_job(job_id: str, **fields) -> None:
    """
    Updates specific fields of an editor job.
    """
    try:
        supabase = get_client()
        response = await asyncio.to_thread(
            lambda: supabase.table("editor_jobs").update(fields).eq("id", job_id).execute()
        )
        if not response.data:
            logger.warning(f"Job {job_id} not found or no fields updated.")
    except Exception as e:
        logger.error(f"Error updating editor job {job_id}: {e}")
        raise RuntimeError(f"Database error: {e}") from e

async def list_editor_jobs(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Lists editor jobs for a specific user, ordered by creation time descending.
    """
    try:
        supabase = get_client()
        response = await asyncio.to_thread(
            lambda: supabase.table("editor_jobs").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Error listing editor jobs for user {user_id}: {e}")
        raise RuntimeError(f"Database error: {e}") from e
