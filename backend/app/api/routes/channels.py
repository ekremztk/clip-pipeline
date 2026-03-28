from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks, Depends
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from app.services.supabase_client import get_client
from app.services import storage
from app.middleware.auth import get_current_user
from app.config import settings
import sys
import os

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

import importlib
try:
    onboarding_worker = importlib.import_module("workers.onboarding_worker")
except Exception:
    onboarding_worker = None

router = APIRouter(prefix="/channels", tags=["channels"])

# YÜKS-3 / DÜŞÜK-3: Allowed upload extensions
_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _safe_ext(filename: str, default: str = ".mp4") -> str:
    """Return a sanitized extension from a filename."""
    ext = os.path.splitext(filename or "")[1].lower()
    return ext if ext in _ALLOWED_VIDEO_EXTS else default


# YÜKS-4: Encrypt/decrypt YouTube tokens at rest using Fernet
def _get_fernet():
    from cryptography.fernet import Fernet
    key = os.getenv("ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("ENCRYPTION_KEY env var is not set — cannot store OAuth tokens")
    return Fernet(key.encode())


def _encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except Exception:
        return value  # Graceful fallback for already-plaintext legacy values


class ChannelCreate(BaseModel):
    channel_id: str
    display_name: str
    niche: Optional[str] = None
    content_format: Optional[str] = None
    clip_duration_min: int = 15
    clip_duration_max: int = 50
    channel_vision: Optional[str] = None

class YouTubeConnect(BaseModel):
    youtube_channel_id: str
    access_token: str
    refresh_token: str

class OnboardExistingRequest(BaseModel):
    youtube_channel_id: str
    youtube_api_key: str

@router.get("")
async def list_channels(current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        result = supabase.table("channels").select("*").eq("user_id", current_user["id"]).order("created_at", desc=True).execute()
        return result.data
    except Exception as e:
        print(f"[ChannelsRoute] Error listing channels: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{channel_id}")
async def get_channel(channel_id: str, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        result = supabase.table("channels").select("*").eq("id", channel_id).eq("user_id", current_user["id"]).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Channel not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ChannelsRoute] Error getting channel: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("")
async def create_channel(channel: ChannelCreate, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        data = {
            "id": channel.channel_id,
            "display_name": channel.display_name,
            "niche": channel.niche,
            "content_format": channel.content_format,
            "clip_duration_min": channel.clip_duration_min,
            "clip_duration_max": channel.clip_duration_max,
            "channel_vision": channel.channel_vision,
            "user_id": current_user["id"]
        }
        supabase.table("channels").insert(data).execute()
        print(f"[ChannelsRoute] Created channel: {channel.channel_id}")
        return {"created": True, "channel_id": channel.channel_id}
    except Exception as e:
        print(f"[ChannelsRoute] Error creating channel: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.patch("/{channel_id}")
async def update_channel(channel_id: str, updates: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    try:
        allowed_fields = {
            "display_name", "niche", "content_format", "clip_duration_min",
            "clip_duration_max", "channel_vision", "channel_dna", "onboarding_status"
        }

        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

        if not filtered_updates:
            return {"updated": False, "channel_id": channel_id, "detail": "No valid fields to update"}

        supabase = get_client()
        result = supabase.table("channels").update(filtered_updates).eq("id", channel_id).eq("user_id", current_user["id"]).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Channel not found")
        print(f"[ChannelsRoute] Updated channel {channel_id}: {list(filtered_updates.keys())}")
        return {"updated": True, "channel_id": channel_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ChannelsRoute] Error updating channel: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{channel_id}/connect-youtube")
async def connect_youtube(channel_id: str, data: YouTubeConnect, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        check = supabase.table("channels").select("id").eq("id", channel_id).eq("user_id", current_user["id"]).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Channel not found")

        # YÜKS-4: Encrypt tokens before storing
        update_data = {
            "youtube_channel_id": data.youtube_channel_id,
            "youtube_access_token": _encrypt(data.access_token),
            "youtube_refresh_token": _encrypt(data.refresh_token),
            "channel_type": "existing"
        }
        supabase.table("channels").update(update_data).eq("id", channel_id).execute()
        print(f"[ChannelsRoute] Connected YouTube for channel: {channel_id}")
        return {"connected": True, "channel_id": channel_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ChannelsRoute] Error connecting YouTube: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{channel_id}/onboard/existing")
async def onboard_existing_channel(channel_id: str, request: OnboardExistingRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        result = supabase.table("channels").select("*").eq("id", channel_id).eq("user_id", current_user["id"]).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Channel not found")

        channel = result.data[0]
        if channel.get("onboarding_status") == "ready":
            raise HTTPException(status_code=400, detail="Channel onboarding already complete")

        update_data = {
            "youtube_channel_id": request.youtube_channel_id
        }
        supabase.table("channels").update(update_data).eq("id", channel_id).execute()

        import importlib
        workers_mod = importlib.import_module("workers.onboarding_worker")

        background_tasks.add_task(
            workers_mod.run_existing_channel_onboarding,
            channel_id,
            request.youtube_channel_id,
            request.youtube_api_key
        )

        return {"started": True, "channel_id": channel_id, "type": "existing"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ChannelsRoute] Error starting existing channel onboarding: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{channel_id}/onboard/new")
async def onboard_new_channel(
    channel_id: str,
    background_tasks: BackgroundTasks,
    files: Optional[List[UploadFile]] = File(None),
    current_user: dict = Depends(get_current_user)
):
    try:
        supabase = get_client()
        result = supabase.table("channels").select("*").eq("id", channel_id).eq("user_id", current_user["id"]).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Channel not found")

        reference_clip_paths = []
        if files:
            for file in files:
                # YÜKS-3: Sanitize filename before saving
                safe_ext = _safe_ext(file.filename)
                import uuid as _uuid
                safe_name = f"{_uuid.uuid4()}{safe_ext}"
                file_bytes = await file.read()
                path = storage.save_upload(file_bytes, safe_name, f"onboard_ref_{channel_id}")
                reference_clip_paths.append(path)

        import importlib
        workers_mod = importlib.import_module("workers.onboarding_worker")

        background_tasks.add_task(
            workers_mod.run_new_channel_onboarding,
            channel_id,
            reference_clip_paths
        )

        return {
            "started": True,
            "channel_id": channel_id,
            "type": "new",
            "reference_clips_count": len(reference_clip_paths)
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ChannelsRoute] Error starting new channel onboarding: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{channel_id}/onboarding-status")
async def get_onboarding_status(channel_id: str, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        result = supabase.table("channels").select("id, onboarding_status, channel_dna").eq("id", channel_id).eq("user_id", current_user["id"]).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Channel not found")

        channel = result.data[0]
        return {
            "channel_id": channel_id,
            "onboarding_status": channel.get("onboarding_status"),
            "channel_dna": channel.get("channel_dna")
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ChannelsRoute] Error getting onboarding status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{channel_id}/references")
async def get_references(channel_id: str, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        check = supabase.table("channels").select("id").eq("id", channel_id).eq("user_id", current_user["id"]).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Channel not found")
        result = supabase.table("reference_clips").select("*").eq("channel_id", channel_id).execute()
        return result.data
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ChannelsRoute] Error getting references: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{channel_id}/references")
async def add_reference(
    channel_id: str,
    file: UploadFile = File(...),
    source_url: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    try:
        supabase = get_client()
        check = supabase.table("channels").select("id").eq("id", channel_id).eq("user_id", current_user["id"]).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Channel not found")

        # DÜŞÜK-3: Sanitize filename
        safe_ext = _safe_ext(file.filename)
        import uuid as _uuid
        safe_name = f"{_uuid.uuid4()}{safe_ext}"

        file_bytes = await file.read()
        storage.save_upload(file_bytes, safe_name, f"ref_{channel_id}")
        print(f"[ChannelsRoute] Saved reference file for channel {channel_id}")

        insert_data = {
            "channel_id": channel_id,
            "user_id": current_user["id"],
            "source": "external_reference",
            "title": os.path.basename(file.filename or "reference")[:100]  # Safe display name only
        }
        if source_url:
            insert_data["source_url"] = source_url

        supabase.table("reference_clips").insert(insert_data).execute()
        print(f"[ChannelsRoute] Added reference clip for channel {channel_id}")

        return {"added": True, "channel_id": channel_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ChannelsRoute] Error adding reference: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
