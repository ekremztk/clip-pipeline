from database import get_client

CONTENT_TYPES = [
    "celebrity_conflict", "hot_take", "funny_reaction", 
    "emotional_reveal", "unexpected_answer", "relatable_moment", 
    "controversial_opinion", "storytelling", "educational_insight"
]

PATTERN_IDS = [
    "celebrity_conflict_reveal", "question_hook", 
    "physical_action_hook", "number_stat_hook", 
    "emotional_reveal_hook", "controversy_hook"
]

DEFAULT_SIGNAL_WEIGHTS = {
    "wpm": 0.10, "has_question": 0.15, "has_exclamation": 0.10,
    "speaker_change": 0.10, "celebrity_name": 0.20,
    "rms_level": 0.05, "rms_spike": 0.10, "silence_before": 0.05,
    "duration_in_golden_zone": 0.10, "content_type_weight": 0.05
}

def get_correlation_rules(channel_id: str) -> list:
    try:
        supabase = get_client()
        response = supabase.table("correlation_rules").select("*").eq("channel_id", channel_id).eq("is_active", True).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"[Correlation] Error in get_correlation_rules: {e}")
        return []

def get_signal_weights(channel_id: str) -> dict:
    try:
        supabase = get_client()
        response = supabase.table("correlation_rules").select("*").eq("channel_id", channel_id).eq("rule_type", "signal_weight").eq("is_active", True).execute()
        
        if not response.data:
            return DEFAULT_SIGNAL_WEIGHTS
            
        weights = {}
        for row in response.data:
            weights[row["rule_key"]] = row.get("weight", 1.0)
            
        # Default değerlerle birleştir / Fallback
        final_weights = DEFAULT_SIGNAL_WEIGHTS.copy()
        final_weights.update(weights)
        
        return final_weights
    except Exception as e:
        print(f"[Correlation] Error in get_signal_weights: {e}")
        return DEFAULT_SIGNAL_WEIGHTS

def update_correlation(channel_id: str, clip_feedback_data: dict) -> bool:
    try:
        supabase = get_client()
        
        rule_type = clip_feedback_data.get("rule_type")
        rule_key = clip_feedback_data.get("rule_key")
        sample_count = clip_feedback_data.get("sample_count", 0)
        
        if not rule_type or not rule_key:
            print("[Correlation] Missing rule_type or rule_key required to update correlation.")
            return False
            
        # Kuralın zaten var olup olmadığını kontrol et
        existing = supabase.table("correlation_rules").select("id").eq("channel_id", channel_id).eq("rule_type", rule_type).eq("rule_key", rule_key).execute()
        
        if not existing.data:
            # Min 10 örnek olmadan yeni kural OLUŞTURMA
            if sample_count < 10:
                print(f"[Correlation] Cannot create new rule for '{rule_key}'. Minimum 10 samples required (current: {sample_count}).")
                return False
                
            new_rule = {
                "channel_id": channel_id,
                "rule_type": rule_type,
                "rule_key": rule_key,
                "sample_count": sample_count,
                "tier4_plus_rate": clip_feedback_data.get("tier4_plus_rate", 0.0),
                "average_rate": clip_feedback_data.get("average_rate", 0.0),
                "weight": clip_feedback_data.get("weight", 1.0),
                "last_30d_rate": clip_feedback_data.get("last_30d_rate", 0.0),
                "last_90d_rate": clip_feedback_data.get("last_90d_rate", 0.0),
                "is_active": True
            }
            supabase.table("correlation_rules").insert(new_rule).execute()
        else:
            # Zaten varsa güncelle
            update_data = {
                "sample_count": sample_count,
                "tier4_plus_rate": clip_feedback_data.get("tier4_plus_rate", 0.0),
                "average_rate": clip_feedback_data.get("average_rate", 0.0),
                "weight": clip_feedback_data.get("weight", 1.0),
                "last_30d_rate": clip_feedback_data.get("last_30d_rate", 0.0),
                "last_90d_rate": clip_feedback_data.get("last_90d_rate", 0.0)
            }
            supabase.table("correlation_rules").update(update_data).eq("id", existing.data[0]["id"]).execute()
            
        return True
    except Exception as e:
        print(f"[Correlation] Error in update_correlation: {e}")
        return False

def check_drift(channel_id: str) -> bool:
    try:
        supabase = get_client()
        response = supabase.table("correlation_rules").select("*").eq("channel_id", channel_id).eq("is_active", True).execute()
        
        if not response.data:
            return False
            
        drift_detected = False
        for rule in response.data:
            last_30d = rule.get("last_30d_rate")
            last_90d = rule.get("last_90d_rate")
            
            if last_30d is not None and last_90d is not None:
                diff = abs(last_30d - last_90d)
                
                # Fark >= 0.15 ise drift_confidence yüksek
                if diff >= 0.15:
                    drift_confidence = diff
                    print(f"[Correlation] Drift detected for {rule['rule_type']} - {rule['rule_key']}: Diff = {diff}")
                    
                    supabase.table("correlation_rules").update({
                        "drift_confidence": float(drift_confidence)
                    }).eq("id", rule["id"]).execute()
                    
                    drift_detected = True
                else:
                    # Geri normale dönmüşse veya baştan düşükse sıfırla
                    supabase.table("correlation_rules").update({
                        "drift_confidence": 0.0
                    }).eq("id", rule["id"]).execute()
                    
        return drift_detected
    except Exception as e:
        print(f"[Correlation] Error in check_drift: {e}")
        return False
