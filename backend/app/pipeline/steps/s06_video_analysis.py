import json
import re

from app.services.gemini_client import analyze_video
from app.pipeline.prompts.video_visual import PROMPT

def run(video_path: str, job_id: str) -> list[dict]:
    """
    Sends the video to Gemini for visual analysis.
    Finds visual events like facial expressions, body language, and reactions.
    """
    print(f"[S06] Starting video analysis for job {job_id}")
    try:
        raw_response = analyze_video(video_path, PROMPT)
        
        # Strip code block wrappers and clean up any control characters
        cleaned = re.sub(r'```json', '', raw_response, flags=re.IGNORECASE)
        cleaned = re.sub(r'```', '', cleaned)
        cleaned = re.sub(r'[\x00-\x1f]', '', cleaned)
        cleaned = cleaned.strip()
        
        try:
            visual_events = json.loads(cleaned)
        except json.JSONDecodeError as json_err:
            print(f"[S06] Error parsing JSON: {json_err}")
            print(f"[S06] Raw response snippet: {cleaned[:200]}")
            return []
            
        if not isinstance(visual_events, list):
            print(f"[S06] Expected list, got {type(visual_events)}")
            return []
            
        print(f"[S06] Found {len(visual_events)} visual events for job {job_id}")
        return visual_events
        
    except Exception as e:
        print(f"[S06] Error during video analysis: {e}")
        return []
