from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from app.services.supabase_client import get_client
from app.services import storage
import sys
import os

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

# Ignore missing imports during Pyre checks; functions are dynamically loaded during runtime
import importlib
try:
    onboarding_worker = importlib.import_module("workers.onboarding_worker")
except Exception:
    onboarding_worker = None

router = APIRouter(prefix="/channels", tags=["channels"])

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
async def list_channels():
    try:
        supabase = get_client()
        result = supabase.table("channels").select("*").order("created_at", desc=True).execute()
        return result.data
    except Exception as e:
        print(f"[ChannelsRoute] Error listing channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{channel_id}")
async def get_channel(channel_id: str):
    try:
        supabase = get_client()
        result = supabase.table("channels").select("*").eq("id", channel_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Channel not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ChannelsRoute] Error getting channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def create_channel(channel: ChannelCreate):
    try:
        supabase = get_client()
        data = {
            "id": channel.channel_id,
            "display_name": channel.display_name,
            "niche": channel.niche,
            "content_format": channel.content_format,
            "clip_duration_min": channel.clip_duration_min,
            "clip_duration_max": channel.clip_duration_max,
            "channel_vision": channel.channel_vision
        }
        supabase.table("channels").insert(data).execute()
        print(f"[ChannelsRoute] Created channel: {channel.channel_id}")
        return {"created": True, "channel_id": channel.channel_id}
    except Exception as e:
        print(f"[ChannelsRoute] Error creating channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{channel_id}")
async def update_channel(channel_id: str, updates: Dict[str, Any]):
    try:
        allowed_fields = {
            "display_name", "niche", "content_format", "clip_duration_min",
            "clip_duration_max", "channel_vision", "channel_dna", "onboarding_status"
        }
        
        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        
        if not filtered_updates:
            return {"updated": False, "channel_id": channel_id, "detail": "No valid fields to update"}
            
        supabase = get_client()
        supabase.table("channels").update(filtered_updates).eq("id", channel_id).execute()
        print(f"[ChannelsRoute] Updated channel {channel_id}: {list(filtered_updates.keys())}")
        return {"updated": True, "channel_id": channel_id}
    except Exception as e:
        print(f"[ChannelsRoute] Error updating channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{channel_id}/connect-youtube")
async def connect_youtube(channel_id: str, data: YouTubeConnect):
    try:
        supabase = get_client()
        update_data = {
            "youtube_channel_id": data.youtube_channel_id,
            "youtube_access_token": data.access_token,
            "youtube_refresh_token": data.refresh_token,
            "channel_type": "existing"
        }
        supabase.table("channels").update(update_data).eq("id", channel_id).execute()
        print(f"[ChannelsRoute] Connected YouTube for channel: {channel_id}")
        return {"connected": True, "channel_id": channel_id}
    except Exception as e:
        print(f"[ChannelsRoute] Error connecting YouTube: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{channel_id}/onboard/existing")
async def onboard_existing_channel(channel_id: str, request: OnboardExistingRequest, background_tasks: BackgroundTasks):
    try:
        supabase = get_client()
        result = supabase.table("channels").select("*").eq("id", channel_id).execute()
        
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
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{channel_id}/onboard/new")
async def onboard_new_channel(
    channel_id: str,
    background_tasks: BackgroundTasks,
    files: Optional[List[UploadFile]] = File(None)
):
    try:
        supabase = get_client()
        result = supabase.table("channels").select("*").eq("id", channel_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Channel not found")
            
        reference_clip_paths = []
        if files:
            for file in files:
                file_bytes = await file.read()
                path = storage.save_upload(file_bytes, file.filename, f"onboard_ref_{channel_id}")
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
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{channel_id}/onboarding-status")
async def get_onboarding_status(channel_id: str):
    try:
        supabase = get_client()
        result = supabase.table("channels").select("id, onboarding_status, channel_dna").eq("id", channel_id).execute()
        
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
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{channel_id}/references")
async def add_reference(
    channel_id: str,
    file: UploadFile = File(...),
    source_url: Optional[str] = Form(None),
    notes: Optional[str] = Form(None)
):
    try:
        supabase = get_client()
        
        file_bytes = await file.read()
        storage.save_upload(file_bytes, file.filename, f"ref_{channel_id}")
        print(f"[ChannelsRoute] Saved reference file {file.filename} for channel {channel_id}")
        
        insert_data = {
            "channel_id": channel_id,
            "source": "external_reference",
            "title": file.filename
        }
        if source_url:
            insert_data["source_url"] = source_url
            
        supabase.table("reference_clips").insert(insert_data).execute()
        print(f"[ChannelsRoute] Added reference clip for channel {channel_id}")
        
        return {"added": True, "channel_id": channel_id}
    except Exception as e:
        print(f"[ChannelsRoute] Error adding reference: {e}")
        raise HTTPException(status_code=500, detail=str(e))
