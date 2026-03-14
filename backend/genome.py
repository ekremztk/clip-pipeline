import math
from database import get_client

def get_genome(channel_id: str) -> dict | None:
    try:
        supabase = get_client()
        response = supabase.table("channel_genome").select("*").eq("channel_id", channel_id).eq("is_active", True).execute()
        
        if not response.data:
            print(f"[Genome] No active genome found for channel_id: {channel_id}")
            return None
            
        return response.data[0]
    except Exception as e:
        print(f"[Genome] Error in get_genome: {e}")
        return None

def calculate_genome(channel_id: str) -> dict | None:
    try:
        supabase = get_client()
        response = supabase.table("viral_library").select("*").eq("channel_id", channel_id).execute()
        data = response.data
        
        if not data:
            print(f"[Genome] No viral_library data found for channel: {channel_id}")
            return None
            
        # 1. Views and Tier Percentiles
        views_list = []
        for row in data:
            v = row.get("views_7d")
            if v is None:
                v = row.get("views_48h")
            if v is None:
                v = row.get("views", 0)
            views_list.append(v)
            
        # Filter purely numeric
        views_list = [v for v in views_list if isinstance(v, (int, float))]
        views_list_sorted = sorted(views_list)
        n_views = len(views_list_sorted)
        
        tier5_threshold = 0
        tier4_threshold = 0
        tier3_threshold = 0
        avg_views = 0
        
        if n_views > 0:
            avg_views = sum(views_list_sorted) / n_views
            tier5_threshold = views_list_sorted[max(0, int(n_views * 0.95))]
            tier4_threshold = views_list_sorted[max(0, int(n_views * 0.80))]
            tier3_threshold = views_list_sorted[max(0, int(n_views * 0.50))]
            
        tier_thresholds = {
            "tier5": tier5_threshold,
            "tier4": tier4_threshold,
            "tier3": tier3_threshold
        }
        
        # 2. Golden Duration (Average ± Std of successful clips)
        successful_clips = [r for r in data if r.get("is_successful") is True]
        durations = [r.get("duration", 0) for r in successful_clips if r.get("duration") is not None]
        
        avg_duration = 0
        std_duration = 0
        if durations:
            avg_duration = sum(durations) / len(durations)
            variance = sum((x - avg_duration) ** 2 for x in durations) / len(durations)
            std_duration = math.sqrt(variance)
            
        golden_duration = {
            "avg": avg_duration,
            "std": std_duration,
            "min": avg_duration - std_duration,
            "max": avg_duration + std_duration
        }
        
        # 3. Content Type Weights
        types_total = {}
        types_success = {}
        for row in data:
            ctype = row.get("content_type")
            if not ctype:
                continue
            types_total[ctype] = types_total.get(ctype, 0) + 1
            if row.get("is_successful") is True:
                types_success[ctype] = types_success.get(ctype, 0) + 1
                
        content_type_weights = {}
        for ctype, t_count in types_total.items():
            s_count = types_success.get(ctype, 0)
            content_type_weights[ctype] = s_count / t_count if t_count > 0 else 0
            
        genome_data = {
            "tier_thresholds": tier_thresholds,
            "golden_duration": golden_duration,
            "content_type_weights": content_type_weights,
            "total_clips_analyzed": len(data),
            "avg_views": int(avg_views)
        }
        
        return genome_data
    except Exception as e:
        print(f"[Genome] Error in calculate_genome: {e}")
        return None

def save_genome(channel_id: str, genome_data: dict) -> bool:
    try:
        supabase = get_client()
        
        # Get current version
        response = supabase.table("channel_genome").select("version_id").eq("channel_id", channel_id).order("version_id", desc=True).limit(1).execute()
        
        old_version = 0
        if response.data:
            old_version = response.data[0].get("version_id", 0)
            
        new_version = old_version + 1
        
        # Mark active to false for existing active genome
        supabase.table("channel_genome").update({"is_active": False}).eq("channel_id", channel_id).eq("is_active", True).execute()
        
        # Insert new version
        new_row = {
            "channel_id": channel_id,
            "version_id": new_version,
            "is_active": True,
            "tier_thresholds": genome_data.get("tier_thresholds", {}),
            "golden_duration": genome_data.get("golden_duration", {}),
            "content_type_weights": genome_data.get("content_type_weights", {}),
            "total_clips_analyzed": genome_data.get("total_clips_analyzed", 0),
            "avg_views": genome_data.get("avg_views", 0)
        }
        
        supabase.table("channel_genome").insert(new_row).execute()
        
        # Keep only the last 5 versions (delete older ones)
        all_versions = supabase.table("channel_genome").select("id, version_id").eq("channel_id", channel_id).order("version_id", desc=True).execute()
        
        if len(all_versions.data) > 5:
            ids_to_delete = [r["id"] for r in all_versions.data[5:]]
            if ids_to_delete:
                supabase.table("channel_genome").delete().in_("id", ids_to_delete).execute()
                
        return True
    except Exception as e:
        print(f"[Genome] Error in save_genome: {e}")
        return False

def rollback_genome(channel_id: str, version_id: int) -> bool:
    try:
        supabase = get_client()
        
        # Check if version exists
        check = supabase.table("channel_genome").select("id").eq("channel_id", channel_id).eq("version_id", version_id).execute()
        if not check.data:
            print(f"[Genome] Version {version_id} not found for channel {channel_id}.")
            return False
            
        # Set all to false
        supabase.table("channel_genome").update({"is_active": False}).eq("channel_id", channel_id).execute()
        
        # Set specified version to true
        supabase.table("channel_genome").update({"is_active": True}).eq("channel_id", channel_id).eq("version_id", version_id).execute()
        
        return True
    except Exception as e:
        print(f"[Genome] Error in rollback_genome: {e}")
        return False
