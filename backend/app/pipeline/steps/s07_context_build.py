from datetime import datetime, timezone, timedelta
from app.config import settings
from app.services.supabase_client import get_client
from app.services.gemini_client import generate_json, embed_content

def get_guest_profile(guest_name: str) -> dict:
    """
    Retrieves or generates a profile for the guest.
    1. Check guest_profiles table first.
    2. If found and not expired, return cached.
    3. Else, use Gemini to generate one and cache it.
    """
    try:
        if not guest_name:
            return {}
            
        supabase = get_client()
        normalized_name = guest_name.strip().lower()
        
        # Check cache
        response = supabase.table("guest_profiles").select("*").eq("normalized_name", normalized_name).execute()
        
        if response.data:
            profile = response.data[0]
            expires_at_str = profile.get("expires_at")
            if expires_at_str:
                # Naive parse, compare with current utc
                # Usually isoformat
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if expires_at > datetime.now(timezone.utc):
                    print(f"[S07] Using cached profile for {guest_name}")
                    return profile.get("profile_data", {})
                    
        print(f"[S07] Generating new profile for {guest_name}")
        prompt = (
            f"Research this person: {guest_name}. Return JSON with:\n"
            f"profile_summary (1 sentence who they are),\n"
            f"recent_topics (list of their recent news/topics, last 30 days),\n"
            f"viral_moments (list of their known viral moments or quotes),\n"
            f"controversies (list of any controversial topics),\n"
            f"expertise_areas (list of their expertise)"
        )
        
        system_instruction = "You are a helpful assistant that outputs ONLY valid JSON."
        profile_data = generate_json(prompt, system=system_instruction)
        
        if not profile_data:
            return {}
            
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        
        # Upsert into database
        upsert_data = {
            "normalized_name": normalized_name,
            "original_name": guest_name,
            "profile_data": profile_data,
            "clip_potential_note": profile_data.get("clip_potential_note", ""),
            "expires_at": expires_at,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if response.data:
            # Update
            supabase.table("guest_profiles").update(upsert_data).eq("normalized_name", normalized_name).execute()
        else:
            # Insert
            supabase.table("guest_profiles").insert(upsert_data).execute()
            
        return profile_data
        
    except Exception as e:
        print(f"[S07] Error in get_guest_profile: {e}")
        return {}

def get_channel_memory(channel_id: str) -> str:
    """
    Retrieves channel memory: success/fail counts, top types, duration, gaps.
    """
    try:
        if not channel_id:
            return ""
            
        supabase = get_client()
        ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        
        # Fetch last 90 days clips for this channel
        response = supabase.table("clips").select("content_type, success_score, duration_s, created_at").eq("channel_id", channel_id).gte("created_at", ninety_days_ago).execute()
        
        clips = response.data
        if not clips:
            return "Channel memory: No recent clips found."
            
        successful_clips = []
        failed_clips = []
        
        # Consider score > 7.0 as successful for this analysis
        for clip in clips:
            score = clip.get("success_score", 0)
            if score >= 7.0:
                successful_clips.append(clip)
            else:
                failed_clips.append(clip)
                
        num_success = len(successful_clips)
        num_failed = len(failed_clips)
        
        type_counts = {}
        total_duration = 0
        
        for clip in successful_clips:
            ctype = clip.get("content_type", "unknown")
            type_counts[ctype] = type_counts.get(ctype, 0) + 1
            total_duration += clip.get("duration_s", 0)
            
        sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        top_types = sorted_types[:3]
        
        avg_duration = total_duration / num_success if num_success > 0 else 0
        
        # Gap analysis (last 30 days)
        recent_type_counts = {}
        for clip in clips:
            if clip.get("created_at") >= thirty_days_ago:
                ctype = clip.get("content_type", "unknown")
                recent_type_counts[ctype] = recent_type_counts.get(ctype, 0) + 1
                
        # Find underrepresented from a known list of types if possible, or just the lowest of the ones we've done
        gap_types = "None"
        if recent_type_counts:
            sorted_recent = sorted(recent_type_counts.items(), key=lambda x: x[1])
            gap_types = f"{sorted_recent[0][0]} underrepresented" if sorted_recent else "None"
            
        # Format strings
        top_types_str = ", ".join([f"{k} ({v} clips)" for k, v in top_types]) if top_types else "None"
        
        summary = (
            f"Channel memory (last 90 days):\n"
            f"- {num_success} successful clips, {num_failed} failed clips\n"
            f"- Top performing types: {top_types_str}\n"
            f"- Avg successful clip duration: {avg_duration:.1f}s\n"
            f"- Content gap (last 30 days): {gap_types}"
        )
        return summary
        
    except Exception as e:
        print(f"[S07] Error in get_channel_memory: {e}")
        return ""

def get_rag_context(channel_id: str, query_text: str, limit: int = 3) -> str:
    """
    Queries reference_clips using pgvector cosine similarity.
    """
    try:
        if not query_text or not channel_id:
            return ""
            
        supabase = get_client()
        
        # Generate embedding
        embedding = embed_content(query_text)
        
        # We need to call a Postgres function to do vector similarity search.
        # Assuming there's a function named 'match_reference_clips' or similar.
        # Let's use the RPC call. If it doesn't exist, we might have to just do a direct query if possible,
        # but supabase client requires RPC for vector search.
        # The requirements say "Query reference_clips table using pgvector cosine similarity"
        # We will assume 'match_reference_clips' function exists:
        # create function match_reference_clips(query_embedding vector(768), match_threshold float, match_count int, p_channel_id text)
        response = supabase.rpc(
            "match_reference_clips",
            {
                "query_embedding": embedding,
                "match_threshold": 0.0, # Get closest regardless of threshold, or some low threshold
                "match_count": limit,
                "p_channel_id": channel_id
            }
        ).execute()
        
        if not response.data:
            return ""
            
        results = ["Similar successful clips from this channel:"]
        for i, clip in enumerate(response.data, 1):
            hook = clip.get("hook", "N/A")
            ctype = clip.get("content_type", "N/A")
            what_worked = clip.get("what_worked", "N/A")
            results.append(f"{i}. Hook: '{hook}' | Type: {ctype} | What worked: {what_worked}")
            
        return "\n".join(results)
        
    except Exception as e:
        print(f"[S07] Error in get_rag_context: {e}")
        return ""

def run(guest_name: str, channel_id: str, video_title: str) -> dict:
    """
    Builds the full context package for Gemini analysis.
    """
    try:
        print(f"[S07] Building context for guest: {guest_name}, channel: {channel_id}")
        
        profile = get_guest_profile(guest_name) if guest_name else {}
        memory = get_channel_memory(channel_id)
        
        query_text = f"Title: {video_title}"
        if guest_name:
            query_text += f", Guest: {guest_name}"
            
        rag = get_rag_context(channel_id, query_text)
        
        context_package = {
            "guest_profile": profile,
            "channel_memory": memory,
            "rag_context": rag
        }
        
        print("[S07] Context build complete")
        return context_package
        
    except Exception as e:
        print(f"[S07] Critical error in run: {e}")
        return {
            "guest_profile": {},
            "channel_memory": "",
            "rag_context": ""
        }
