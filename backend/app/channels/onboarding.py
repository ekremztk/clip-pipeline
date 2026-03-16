from app.services.supabase_client import get_client
from app.config import settings

def get_channel(channel_id: str) -> dict | None:
    try:
        supabase = get_client()
        print(f"[Onboarding] Fetching channel: {channel_id}")
        response = supabase.table("channels").select("*").eq("id", channel_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        print(f"[Onboarding] Error fetching channel {channel_id}: {e}")
        return None

def update_onboarding_status(channel_id: str, status: str) -> None:
    try:
        valid_statuses = ["setup", "connecting", "scanning", "analyzing", "ready"]
        if status not in valid_statuses:
            print(f"[Onboarding] Warning: '{status}' is not a recognized onboarding status.")
            
        supabase = get_client()
        print(f"[Onboarding] Updating channel {channel_id} status to: {status}")
        supabase.table("channels").update({"onboarding_status": status}).eq("id", channel_id).execute()
    except Exception as e:
        print(f"[Onboarding] Error updating onboarding status for {channel_id}: {e}")

def create_new_channel(channel_data: dict) -> dict:
    try:
        supabase = get_client()
        channel_id = channel_data.get("id")
        
        if not channel_id:
            raise ValueError("Channel ID is required")
            
        print(f"[Onboarding] Creating new channel: {channel_id}")
        
        existing = get_channel(channel_id)
        if existing:
            raise ValueError(f"Channel {channel_id} already exists")
            
        insert_data = {
            "id": channel_id,
            "display_name": channel_data.get("display_name"),
            "niche": channel_data.get("niche"),
            "content_format": channel_data.get("content_format"),
            "target_platforms": channel_data.get("target_platforms", ["youtube_shorts"]),
            "clip_duration_min": channel_data.get("clip_duration_min", 15),
            "clip_duration_max": channel_data.get("clip_duration_max", 50),
            "channel_type": "new",
            "onboarding_status": "setup",
            "channel_vision": channel_data.get("channel_vision"),
            "channel_dna": {}
        }
        
        response = supabase.table("channels").insert(insert_data).execute()
        if response.data and len(response.data) > 0:
            print(f"[Onboarding] Successfully created channel {channel_id}")
            return response.data[0]
            
        raise Exception("Insert failed, no data returned")
        
    except ValueError:
        raise
    except Exception as e:
        print(f"[Onboarding] Error creating new channel: {e}")
        raise

def set_channel_dna(channel_id: str, dna: dict) -> None:
    try:
        supabase = get_client()
        print(f"[Onboarding] Setting channel DNA for {channel_id}")
        supabase.table("channels").update({
            "channel_dna": dna,
            "onboarding_status": "ready"
        }).eq("id", channel_id).execute()
    except Exception as e:
        print(f"[Onboarding] Error setting channel DNA for {channel_id}: {e}")

def get_onboarding_status(channel_id: str) -> str:
    try:
        print(f"[Onboarding] Getting status for {channel_id}")
        channel = get_channel(channel_id)
        if channel and "onboarding_status" in channel:
            return channel["onboarding_status"]
        
        print(f"[Onboarding] Channel {channel_id} not found or missing status")
        return "unknown"
    except Exception as e:
        print(f"[Onboarding] Error getting status for {channel_id}: {e}")
        return "unknown"
