import os
import json
import urllib.request
import requests
from datetime import datetime, timezone, timedelta

from app.services.supabase_client import get_client

def fetch_youtube_metrics(youtube_video_id: str, api_key: str) -> dict | None:
    try:
        url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={youtube_video_id}&key={api_key}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("items"):
            print(f"[FeedbackWorker] No items found for video ID: {youtube_video_id}")
            return None
            
        stats = data["items"][0].get("statistics", {})
        
        return {
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0))
        }
    except Exception as e:
        print(f"[FeedbackWorker] Error fetching metrics for {youtube_video_id}: {e}")
        return None

def calculate_channel_averages(channel_id: str) -> dict:
    try:
        supabase = get_client()
        response = supabase.table("clips") \
            .select("views_7d, avd_pct") \
            .eq("channel_id", channel_id) \
            .not_.is_("is_successful", "null") \
            .not_.is_("views_7d", "null") \
            .execute()
        
        data = response.data
        if not data:
            return {"avg_views_7d": 0.0, "avg_avd_pct": 0.0}
            
        total_views = 0.0
        total_avd = 0.0
        avd_count = 0
        
        for row in data:
            total_views += float(row.get("views_7d", 0))
            if row.get("avd_pct") is not None:
                total_avd += float(row.get("avd_pct"))
                avd_count += 1
                
        avg_views = total_views / len(data)
        avg_avd = (total_avd / avd_count) if avd_count > 0 else 0.0
        
        return {"avg_views_7d": float(avg_views), "avg_avd_pct": float(avg_avd)}
    except Exception as e:
        print(f"[FeedbackWorker] Error calculating averages for channel {channel_id}: {e}")
        return {"avg_views_7d": 0.0, "avg_avd_pct": 0.0}

def label_clip(clip: dict, channel_averages: dict) -> dict:
    try:
        result = {"is_successful": False}
        
        views_7d = float(clip.get("views_7d", 0))
        avg_views_7d = float(channel_averages.get("avg_views_7d", 0))
        
        if views_7d > avg_views_7d * 1.5:
            result["is_successful"] = True
            
        avd_pct = clip.get("avd_pct")
        if avd_pct is not None:
            avd_pct = float(avd_pct)
            avg_avd_pct = float(channel_averages.get("avg_avd_pct", 0))
            if avd_pct > avg_avd_pct * 1.15:
                result["avd_success"] = True
            else:
                result["avd_success"] = False
                
        return result
    except Exception as e:
        print(f"[FeedbackWorker] Error labeling clip: {e}")
        return {"is_successful": False}

def notify_rag_candidate(clip: dict) -> None:
    try:
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            print("[FeedbackWorker] DISCORD_WEBHOOK_URL not set, skipping notification.")
            return
            
        payload = {
            "content": "New RAG candidate ready for review",
            "embeds": [{
                "title": f"Clip from Channel: {clip.get('channel_id')}",
                "description": f"**Hook:** {clip.get('hook_text')}\n**Views (7d):** {clip.get('views_7d')}\n**Posting Order:** {clip.get('posting_order')}",
                "footer": {"text": f"Clip ID: {clip.get('id')}"}
            }]
        }
        
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Prognot/1.0"}
        )
        
        with urllib.request.urlopen(req) as response:
            if response.status not in (200, 204):
                print(f"[FeedbackWorker] Discord webhook returned status {response.status}")
                
    except Exception as e:
        print(f"[FeedbackWorker] Error sending Discord notification: {e}")

def check_pending_clips() -> None:
    try:
        supabase = get_client()
        youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
        if not youtube_api_key:
            print("[FeedbackWorker] Error: YOUTUBE_API_KEY environment variable is not set")
            return

        print("[FeedbackWorker] Starting check_pending_clips...")
        
        now = datetime.now(timezone.utc)
        date_48h_ago_str = (now - timedelta(hours=48)).isoformat()
        date_7d_ago_str = (now - timedelta(days=7)).isoformat()
        
        # Step A — 48 hour check
        print(f"[FeedbackWorker] Checking for 48h clips (published before {date_48h_ago_str})")
        resp_48h = supabase.table("clips") \
            .select("*") \
            .eq("feedback_status", "pending") \
            .not_.is_("published_at", "null") \
            .not_.is_("youtube_video_id", "null") \
            .lt("published_at", date_48h_ago_str) \
            .execute()
            
        clips_48h = resp_48h.data or []
        for clip in clips_48h:
            try:
                metrics = fetch_youtube_metrics(clip["youtube_video_id"], youtube_api_key)
                if metrics:
                    supabase.table("clips").update({
                        "views_48h": metrics["views"],
                        "feedback_status": "preliminary_48h"
                    }).eq("id", clip["id"]).execute()
                    print(f"[FeedbackWorker] Updated 48h metrics for clip {clip['id']}")
            except Exception as e:
                print(f"[FeedbackWorker] Error processing 48h clip {clip.get('id')}: {e}")
                
        # Step B — 7 day check
        print(f"[FeedbackWorker] Checking for 7d clips (published before {date_7d_ago_str})")
        resp_7d = supabase.table("clips") \
            .select("*") \
            .eq("feedback_status", "preliminary_48h") \
            .not_.is_("published_at", "null") \
            .not_.is_("youtube_video_id", "null") \
            .lt("published_at", date_7d_ago_str) \
            .execute()
            
        clips_7d = resp_7d.data or []
        for clip in clips_7d:
            try:
                metrics = fetch_youtube_metrics(clip["youtube_video_id"], youtube_api_key)
                if not metrics:
                    continue
                    
                clip_for_label = clip.copy()
                clip_for_label["views_7d"] = metrics["views"]
                
                avgs = calculate_channel_averages(clip["channel_id"])
                label_res = label_clip(clip_for_label, avgs)
                
                update_data = {
                    "views_7d": metrics["views"],
                    "likes": metrics["likes"],
                    "comments": metrics["comments"],
                    "feedback_status": "final_7d",
                    "is_successful": label_res["is_successful"]
                }
                
                if "avd_success" in label_res:
                    update_data["avd_success"] = label_res["avd_success"]
                    
                if label_res["is_successful"]:
                    update_data["needs_rag_review"] = True
                    
                supabase.table("clips").update(update_data).eq("id", clip["id"]).execute()
                print(f"[FeedbackWorker] Updated 7d metrics for clip {clip['id']}, successful: {label_res['is_successful']}")
                
                if label_res["is_successful"]:
                    try:
                        channel_id = clip["channel_id"]
                        chan_resp = supabase.table("channels").select("successful_clips_count").eq("id", channel_id).execute()
                        if chan_resp.data:
                            current_count = chan_resp.data[0].get("successful_clips_count") or 0
                            supabase.table("channels").update({
                                "successful_clips_count": current_count + 1
                            }).eq("id", channel_id).execute()
                    except Exception as e:
                        print(f"[FeedbackWorker] Error updating channel count: {e}")
                        
                    clip_for_notify = clip.copy()
                    clip_for_notify["views_7d"] = metrics["views"]
                    notify_rag_candidate(clip_for_notify)
                    
            except Exception as e:
                print(f"[FeedbackWorker] Error processing 7d clip {clip.get('id')}: {e}")

        print(f"[FeedbackWorker] Summary: Processed {len(clips_48h)} 48h clips, {len(clips_7d)} 7d clips.")
        
    except Exception as e:
        print(f"[FeedbackWorker] Fatal error in check_pending_clips: {e}")

if __name__ == "__main__":
    check_pending_clips()
