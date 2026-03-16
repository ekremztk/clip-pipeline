import json
import os
import subprocess
import tempfile
from typing import Optional, Dict, Any

from app.config import settings
from app.services.gemini_client import generate, generate_json
from app.services.supabase_client import get_client
from app.services import deepgram_client
from app.pipeline.prompts.clip_summary import PROMPT as clip_summary_prompt_template
from app.pipeline.prompts.channel_dna import PROMPT as channel_dna_prompt_template
from app.channels import youtube_importer

def analyze_single_clip(video_path: str, channel_id: str, source: str, source_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Extracts audio, transcribes, summarizes, and adds a reference clip to the database.
    """
    audio_path = None
    try:
        print(f"[ReferenceAnalyzer] Starting analysis for video: {video_path}")
        
        # 1. Extract audio
        fd, audio_path = tempfile.mkstemp(suffix=".m4a")
        os.close(fd)
        
        command = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-c:a", "aac", "-b:a", "192k",
            audio_path
        ]
        
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # 2. Transcribe
        transcript_data = deepgram_client.transcribe(audio_path)
        if not transcript_data or "transcript" not in transcript_data:
            print("[ReferenceAnalyzer] Failed to transcribe video.")
            return None
            
        transcript = transcript_data["transcript"]
        
        # 3. Build clip_summary prompt
        clip_data = {
            "transcript": transcript,
            "source_url": source_url,
            "channel_id": channel_id
        }
        
        prompt = clip_summary_prompt_template.replace("CLIP_DATA_PLACEHOLDER", json.dumps(clip_data))
        
        # 4. Generate summary
        summary = generate(prompt, model=settings.GEMINI_MODEL_FLASH)
        
        # 5. Insert into reference_clips table
        supabase = get_client()
        data = {
            "channel_id": channel_id,
            "source": source,
            "source_url": source_url,
            "transcript": transcript,
            "clip_summary": summary,
            "analyzed_at": "now()"
        }
        
        result = supabase.table("reference_clips").insert(data).execute()
        
        if result.data and len(result.data) > 0:
            print("[ReferenceAnalyzer] Successfully analyzed and saved reference clip.")
            return result.data[0]
        else:
            print("[ReferenceAnalyzer] Failed to insert reference clip into database.")
            return None
            
    except Exception as e:
        print(f"[ReferenceAnalyzer] Error analyzing single clip: {e}")
        return None
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)


def analyze_channel_history(channel_id: str, successful_shorts: list) -> int:
    """
    Analyzes up to 20 successful shorts for a channel.
    """
    try:
        print(f"[ReferenceAnalyzer] Analyzing channel history for {channel_id} with {len(successful_shorts)} shorts")
        
        shorts_to_analyze = successful_shorts[:20]
        success_count = 0
        
        temp_dir = tempfile.mkdtemp()
        
        for short in shorts_to_analyze:
            video_id = short.get("video_id")
            if not video_id:
                continue
                
            print(f"[ReferenceAnalyzer] Processing short: {video_id}")
            
            video_path = youtube_importer.download_short(video_id, temp_dir)
            if not video_path:
                print(f"[ReferenceAnalyzer] Failed to download short: {video_id}")
                continue
                
            try:
                source_url = f"https://www.youtube.com/shorts/{video_id}"
                clip_data = analyze_single_clip(
                    video_path=video_path,
                    channel_id=channel_id,
                    source="own_successful",
                    source_url=source_url
                )
                
                if clip_data:
                    # Update with performance data
                    supabase = get_client()
                    update_data = {
                        "views": short.get("view_count", 0),
                        "performance_data": short
                    }
                    supabase.table("reference_clips").update(update_data).eq("id", clip_data["id"]).execute()
                    success_count += 1
                    
            finally:
                if video_path and os.path.exists(video_path):
                    os.remove(video_path)
                    
        print(f"[ReferenceAnalyzer] Successfully analyzed {success_count} shorts for channel {channel_id}")
        return success_count
        
    except Exception as e:
        print(f"[ReferenceAnalyzer] Error analyzing channel history: {e}")
        return 0


def build_channel_dna(channel_id: str) -> Optional[Dict[str, Any]]:
    """
    Builds the channel DNA based on successfully analyzed reference clips.
    """
    try:
        print(f"[ReferenceAnalyzer] Building channel DNA for {channel_id}")
        
        supabase = get_client()
        result = supabase.table("reference_clips") \
            .select("*") \
            .eq("channel_id", channel_id) \
            .eq("source", "own_successful") \
            .order("views", desc=True) \
            .limit(20) \
            .execute()
            
        clips = result.data if result else []
        
        if len(clips) < 3:
            print(f"[ReferenceAnalyzer] Not enough clips to build channel DNA. Found {len(clips)}, need at least 3.")
            return None
            
        prompt = channel_dna_prompt_template.replace("CLIPS_DATA_PLACEHOLDER", json.dumps(clips))
        
        dna_data = generate_json(prompt, model=settings.GEMINI_MODEL_PRO)
        
        print(f"[ReferenceAnalyzer] Successfully built channel DNA for {channel_id}")
        return dna_data
        
    except Exception as e:
        print(f"[ReferenceAnalyzer] Error building channel DNA: {e}")
        return None
