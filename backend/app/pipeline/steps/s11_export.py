import os
import subprocess
import traceback
import uuid
from app.config import settings
from app.services.supabase_client import get_client
from app.services.r2_client import upload_clip

def run(cut_results: list, job_id: str) -> list:
    """
    Step 11: Export
    This is the final step — produces the highest quality 16:9 MP4 output files.
    """
    print(f"[S11] Starting export for {len(cut_results)} clips. Job ID: {job_id}")
    exported_clips = []
    
    supabase = get_client()

    for index, clip in enumerate(cut_results):
        try:
            input_path = clip.get("video_landscape_path")
            
            # 1. Verify video_landscape_path exists and file size > 0
            if not input_path or not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
                print(f"[S11] Error: Input video missing or empty for clip {clip.get('clip_index', 'unknown')}. Skipping.")
                continue

            # 2. Re-encode for maximum quality output
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_final{ext}"
            
            print(f"[S11] Re-encoding {input_path} to {output_path}")
            
            # FFmpeg command:
            # ffmpeg -y -i {input_path} -c:v libx264 -preset slow -crf 18 -c:a aac -b:a 320k -movflags +faststart -pix_fmt yuv420p {output_path}
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-c:a", "aac", "-b:a", "320k",
                "-movflags", "+faststart",
                "-pix_fmt", "yuv420p",
                output_path
            ]
            
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 3. Verify output file exists and size > 0
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                print(f"[S11] Error: Output video missing or empty for clip {clip.get('clip_index', 'unknown')}. Skipping.")
                continue

            # 4. Upload to Cloudflare R2
            filename = os.path.basename(output_path)
            file_url = output_path  # Default to local path as fallback
            try:
                print(f"[S11] Uploading {filename} to R2...")
                r2_url = upload_clip(job_id, filename, output_path)
                print(f"[S11] Successfully uploaded to R2: {r2_url}")
                file_url = r2_url
                
                # Delete the local file after successful upload
                try:
                    os.remove(output_path)
                except Exception as cleanup_err:
                    print(f"[S11] Warning: Failed to delete local file {output_path}: {cleanup_err}")
            except Exception as r2_err:
                print(f"[S11] Error: Failed to upload to R2: {r2_err}")
                print("[S11] Using local path as fallback.")

            # 5. Update clips table in Supabase
            clip_data = {
                "clip_index": index,
                "id": str(uuid.uuid4()),
                "job_id": job_id,
                "channel_id": clip.get("channel_id", "speedy_cast"),
                "start_time": clip.get("final_start") or clip.get("start_time") or 0,
                "end_time": clip.get("final_end") or clip.get("end_time") or 0,
                "duration_s": clip.get("duration_s") or 0,
                "hook_text": clip.get("hook_text") or "",
                "content_type": clip.get("content_type") or "general",
                "clip_strategy_role": clip.get("clip_strategy_role") or "context_builder",
                "posting_order": clip.get("posting_order") or 0,
                "standalone_score": clip.get("standalone_score") or 0,
                "hook_score": clip.get("hook_score") or 0,
                "arc_score": clip.get("arc_score") or 0,
                "channel_fit_score": clip.get("channel_fit_score") or 0,
                "quality_status": clip.get("quality_status") or "fixable",
                "quality_notes": clip.get("quality_notes") or "",
                "video_landscape_path": output_path or "",
                "file_url": file_url
            }
            
            insert_result = supabase.table("clips").insert(clip_data).execute()
            
            if not insert_result.data:
                print(f"[S11] Error: Failed to insert clip {clip.get('clip_index', 'unknown')} into Supabase.")
                continue
                
            clip_id = insert_result.data[0].get("id")
            print(f"[S11] Successfully exported and inserted clip {clip.get('clip_index', 'unknown')} with ID {clip_id}")
            
            # 6. Add to result
            exported_clips.append({
                "clip_id": clip_id,
                "final_path": output_path,
                "file_url": file_url,
                "export_status": "success"
            })
            
        except Exception as e:
            print(f"[S11] Error processing clip {clip.get('clip_index', 'unknown')}: {e}")
            traceback.print_exc()
            continue

    print(f"[S11] Summary: {len(exported_clips)} clips exported successfully.")
    return exported_clips
