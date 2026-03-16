import json
from app.services.gemini_client import generate, generate_json, embed_content
from app.services.supabase_client import get_client
from app.pipeline.prompts.failure_analysis import PROMPT as FAILURE_ANALYSIS_PROMPT
from app.pipeline.prompts.clip_summary import PROMPT as CLIP_SUMMARY_PROMPT
from app.config import settings

def process_successful_clip(clip: dict) -> None:
    try:
        # Generate natural language summary for RAG
        prompt = CLIP_SUMMARY_PROMPT.replace("CLIP_DATA_PLACEHOLDER", json.dumps(clip))
        summary_text = generate(prompt, model=settings.GEMINI_MODEL_FLASH)
        
        # Generate embedding for the summary
        embedding = embed_content(summary_text)
        
        supabase = get_client()
        
        # Update clips table
        supabase.table("clips").update({
            "clip_summary": summary_text,
            "clip_summary_embedding": embedding
        }).eq("id", clip["id"]).execute()
        
        # Insert into reference_clips table
        reference_data = {
            "channel_id": clip.get("channel_id"),
            "source": "own_successful",
            "source_clip_id": clip["id"],
            "hook_text": clip.get("hook_text"),
            "content_type": clip.get("content_type"),
            "duration_s": clip.get("duration_s"),
            "views": clip.get("views_7d"),
            "clip_summary": summary_text,
            "clip_summary_embedding": embedding,
            "what_makes_it_work": summary_text
        }
        
        supabase.table("reference_clips").insert(reference_data).execute()
        
        print("[FeedbackProcessor] clip processed successfully")
    except Exception as e:
        print(f"[FeedbackProcessor] Error processing successful clip: {e}")

def process_failed_clip(clip: dict) -> None:
    try:
        # Build failure_analysis prompt
        clip_data = {
            "hook_text": clip.get("hook_text"),
            "content_type": clip.get("content_type"),
            "duration_s": clip.get("duration_s"),
            "standalone_score": clip.get("standalone_score"),
            "hook_score": clip.get("hook_score"),
            "arc_score": clip.get("arc_score")
        }
        performance_data = {
            "views_7d": clip.get("views_7d"),
            "avd_pct": clip.get("avd_pct")
        }
        
        prompt = FAILURE_ANALYSIS_PROMPT.replace("CLIP_DATA_PLACEHOLDER", json.dumps(clip_data))
        prompt = prompt.replace("PERFORMANCE_DATA_PLACEHOLDER", json.dumps(performance_data))
        
        analysis_result = generate_json(prompt, model=settings.GEMINI_MODEL_FLASH)
        
        supabase = get_client()
        
        # Update clips table
        supabase.table("clips").update({
            "why_failed": json.dumps(analysis_result)
        }).eq("id", clip["id"]).execute()
        
        print("[FeedbackProcessor] failure analysis complete")
    except Exception as e:
        print(f"[FeedbackProcessor] Error processing failed clip: {e}")

def update_channel_averages(channel_id: str) -> None:
    try:
        supabase = get_client()
        
        # Query clips
        response = supabase.table("clips").select("views_7d").eq("channel_id", channel_id).eq("feedback_status", "final_7d").not_("views_7d", "is", "null").execute()
        
        clips = response.data
        if not clips:
            print(f"[FeedbackProcessor] No clips found for channel {channel_id}")
            return
            
        successful_clips_count = len(clips)
        total_views = sum(clip["views_7d"] for clip in clips if clip.get("views_7d") is not None)
        calculated_avg = total_views / successful_clips_count if successful_clips_count > 0 else 0
        
        # Update channels table
        supabase.table("channels").update({
            "avg_views_7d": calculated_avg,
            "successful_clips_count": successful_clips_count
        }).eq("id", channel_id).execute()
        
        print(f"[FeedbackProcessor] Channel averages updated for {channel_id}")
    except Exception as e:
        print(f"[FeedbackProcessor] Error updating channel averages: {e}")