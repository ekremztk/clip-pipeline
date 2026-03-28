import os
import subprocess
import traceback
from app.config import settings
from app.services.supabase_client import get_client
from app.services.r2_client import upload_clip
from app.director.events import director_events


def run(cut_results: list, job_id: str, channel_id: str, video_path: str, video_title: str = "", user_id: str | None = None) -> list:
    """
    Step 8: Export
    For each clip: FFmpeg frame-accurate cut + encode → R2 upload → Supabase insert.
    Single FFmpeg call per clip — no intermediate files, no double encoding.
    """
    print(f"[S08] Starting export for {len(cut_results)} clips. Job: {job_id}")
    exported_clips = []
    supabase = get_client()

    # Ensure output directory exists
    job_output_dir = os.path.join(settings.OUTPUT_DIR, job_id)
    os.makedirs(job_output_dir, exist_ok=True)

    for index, clip in enumerate(cut_results):
        output_path = None
        try:
            final_start = clip.get("final_start", 0.0)
            final_duration = clip.get("final_duration_s", 0.0)
            content_type = clip.get("content_type", "unknown")
            candidate_id = clip.get("candidate_id", index)

            if final_duration <= 0:
                print(f"[S08] Clip {index+1}: Invalid duration ({final_duration}s). Skipping.")
                continue

            # 1. FFmpeg: frame-accurate cut + high-quality encode in ONE call
            output_filename = f"clip_{index:02d}_{content_type}.mp4"
            output_path = os.path.join(job_output_dir, output_filename)

            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-ss", str(final_start),
                "-i", video_path,
                "-t", str(final_duration),
                "-c:v", "libx264",
                "-preset", settings.FFMPEG_PRESET,       # "slow"
                "-crf", str(settings.FFMPEG_CRF),         # 18
                "-c:a", "aac",
                "-b:a", "320k",
                "-movflags", "+faststart",
                "-pix_fmt", "yuv420p",
                "-avoid_negative_ts", "make_zero",
                "-map", "0:v:0",
                "-map", "0:a:0",
                output_path
            ]

            print(f"[S08] Clip {index+1}/{len(cut_results)}: Cutting {final_start:.2f}s + {final_duration:.1f}s [{content_type}]")
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

            # 2. Verify output
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                print(f"[S08] Error: Output missing or empty for clip {index+1}. Skipping.")
                continue

            # 3. Upload to Cloudflare R2
            file_url = output_path  # fallback
            try:
                r2_url = upload_clip(job_id, output_filename, output_path)
                print(f"[S08] Uploaded to R2: {r2_url}")
                file_url = r2_url
            except Exception as r2_err:
                print(f"[S08] R2 upload failed: {r2_err}. Using local path.")

            # 4. Insert into Supabase clips table
            clip_data = {
                "job_id": job_id,
                "channel_id": channel_id,
                "user_id": user_id,
                "clip_index": index,
                "start_time": float(final_start),
                "end_time": float(clip.get("final_end", 0.0)),
                "duration_s": float(final_duration),
                "hook_text": clip.get("hook_text"),
                "content_type": content_type,
                "confidence": clip.get("overall_confidence"),
                "standalone_score": clip.get("standalone_score"),
                "hook_score": clip.get("hook_score"),
                "arc_score": clip.get("arc_score"),
                "channel_fit_score": clip.get("channel_fit_score"),
                "thinking_steps": clip.get("thinking_steps"),
                "standalone_result": clip.get("quality_verdict"),
                "clip_strategy_role": clip.get("clip_strategy_role"),
                "posting_order": clip.get("posting_order"),
                "suggested_title": clip.get("suggested_title"),
                "suggested_description": clip.get("suggested_description"),
                "video_landscape_path": file_url,
                "file_url": file_url,
                "is_successful": None,  # user sets this manually via approve/reject UI
                "quality_notes": clip.get("reject_reason"),  # populated only for fixable clips
            }

            # Remove None values to avoid Supabase errors
            clip_data = {k: v for k, v in clip_data.items() if v is not None}

            try:
                result = supabase.table("clips").insert(clip_data).execute()
                if result.data:
                    clip_id = result.data[0].get("id")
                    print(f"[S08] Clip {index+1} saved to DB (id: {clip_id})")
                    exported_clips.append(result.data[0])
                else:
                    print(f"[S08] Warning: DB insert returned no data for clip {index+1}")
                    exported_clips.append(clip_data)
            except Exception as db_err:
                print(f"[S08] DB insert error for clip {index+1}: {db_err}")
                exported_clips.append(clip_data)

            # 5. Clean up local file after successful R2 upload
            if file_url != output_path:
                try:
                    os.remove(output_path)
                except Exception:
                    pass

        except subprocess.CalledProcessError as e:
            stderr_output = e.stderr.decode() if e.stderr else "no stderr"
            print(f"[S08] FFmpeg error for clip {index+1}: {stderr_output[:500]}")
        except Exception as e:
            print(f"[S08] Unexpected error for clip {index+1}: {e}")
            traceback.print_exc()
        finally:
            # Clean up output file if it exists and wasn't uploaded
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass

    print(f"[S08] Export complete. {len(exported_clips)}/{len(cut_results)} clips exported.")
    try:
        director_events.emit_sync(
            module="module_1", event="s08_export_completed",
            payload={"job_id": job_id, "exported_count": len(exported_clips)},
            channel_id=channel_id,
        )
    except Exception:
        pass
    return exported_clips
