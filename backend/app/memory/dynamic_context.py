import datetime
from app.services.supabase_client import get_client
from app.models.enums import ContentType

def build_channel_memory(channel_id: str, days: int = 90) -> str:
    try:
        supabase = get_client()
        cutoff_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
        
        response = supabase.table("clips").select("*").eq("channel_id", channel_id).eq("feedback_status", "final_7d").gte("created_at", cutoff_date).execute()
        clips = response.data
        
        if not clips:
            return "No channel memory yet — using general viral content patterns."
            
        successful_clips = [c for c in clips if c.get("is_successful")]
        failed_clips = [c for c in clips if not c.get("is_successful")]
        
        # WHAT WORKED
        succ_types = {}
        for c in successful_clips:
            ct = c.get("content_type")
            if ct:
                succ_types[ct] = succ_types.get(ct, 0) + 1
        sorted_succ_types = sorted(succ_types.items(), key=lambda x: x[1], reverse=True)[:3]
        succ_types_str = ", ".join([f"{k} ({v})" for k, v in sorted_succ_types]) if sorted_succ_types else "None"
        
        durations = [c.get("duration", 0) for c in successful_clips if c.get("duration")]
        avg_dur = sum(durations) / len(durations) if durations else 0
        
        hooks = [c.get("hook_text") for c in successful_clips if c.get("hook_text")]
        hooks_str = ", ".join([f'"{h}"' for h in hooks[:3]]) if hooks else "None"
        
        # Content gap
        cutoff_30d = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()
        clips_30d = [c for c in clips if c.get("created_at") and c.get("created_at") >= cutoff_30d]
        types_30d = {c.get("content_type") for c in clips_30d if c.get("content_type")}
        all_types = {ct.value for ct in ContentType}
        gap_types = all_types - types_30d
        gap_str = ", ".join(sorted(list(gap_types))) if gap_types else "None"
        
        # WHAT FAILED
        fail_types = {}
        for c in failed_clips:
            ct = c.get("content_type")
            if ct:
                fail_types[ct] = fail_types.get(ct, 0) + 1
        sorted_fail_types = sorted(fail_types.items(), key=lambda x: x[1], reverse=True)
        fail_types_str = ", ".join([f"{k} ({v})" for k, v in sorted_fail_types]) if sorted_fail_types else "None"
        
        reasons = {}
        for c in failed_clips:
            wf = c.get("why_failed")
            if wf:
                reasons[wf] = reasons.get(wf, 0) + 1
        sorted_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:3]
        reasons_str = ", ".join([f"{k} ({v})" if v > 1 else k for k, v in sorted_reasons]) if sorted_reasons else "None"
        
        # Channel averages
        views = [c.get("views_7d", 0) for c in clips if c.get("views_7d") is not None]
        avg_views = sum(views) / len(views) if views else 0
        
        avds = [c.get("avd_pct", 0) for c in clips if c.get("avd_pct") is not None]
        avg_avd = sum(avds) / len(avds) if avds else 0
        
        memory_str = f"""Channel memory (last {days} days):

WHAT WORKED ({len(successful_clips)} clips):
- Content types: {succ_types_str}
- Avg successful duration: {avg_dur:.1f}s
- Top hooks: {hooks_str}
- Content gap (underrepresented last 30 days): {gap_str}

WHAT FAILED ({len(failed_clips)} clips):
- Failed content types: {fail_types_str}
- Common failure reasons: {reasons_str}

Channel averages: {avg_views:.1f} views, {avg_avd:.1f}% AVD"""
        
        return memory_str
        
    except Exception as e:
        print(f"[DynamicContext] Error in build_channel_memory: {e}")
        return ""

def build_cold_start_context(niche: str, content_format: str) -> str:
    try:
        niche_lower = (niche or "").lower()
        
        if "entertainment" in niche_lower or "celebrity" in niche_lower:
            return (
                "General patterns for entertainment clips: shocking reveals and funny reactions "
                "perform best. Keep under 40 seconds. Start with the most surprising statement."
            )
            
        if "tech" in niche_lower or "business" in niche_lower:
            return (
                "General patterns for tech/business clips: contrarian takes and unexpected "
                "insights perform best. Keep under 45 seconds. Start with a bold claim."
            )
            
        return (
            "No channel history available. Focus on strong hooks, complete story arcs, "
            "and moments that are understandable without prior context."
        )
        
    except Exception as e:
        print(f"[DynamicContext] Error in build_cold_start_context: {e}")
        return ""

def get_full_context(channel_id: str) -> str:
    try:
        supabase = get_client()
        channel_res = supabase.table("channels").select("niche, content_format, channel_dna").eq("id", channel_id).execute()
        
        if not channel_res.data:
            print(f"[DynamicContext] Channel {channel_id} not found.")
            return build_cold_start_context("", "")
            
        channel = channel_res.data[0]
        niche = channel.get("niche", "")
        content_format = channel.get("content_format", "")
        
        clips_res = supabase.table("clips").select("id").eq("channel_id", channel_id).eq("feedback_status", "final_7d").limit(5).execute()
        clip_count = len(clips_res.data) if clips_res.data else 0
        
        if clip_count >= 5:
            return build_channel_memory(channel_id)
        else:
            return build_cold_start_context(niche, content_format)
            
    except Exception as e:
        print(f"[DynamicContext] Error in get_full_context: {e}")
        return ""
