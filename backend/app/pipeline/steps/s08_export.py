import os
import re
import subprocess
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from app.config import settings
from app.ffmpeg_encode import append_pipeline_audio_encode_args, append_pipeline_video_encode_args
from app.services.supabase_client import get_client
from app.services.r2_client import upload_clip
from app.director.events import director_events
from app.pipeline.stock_analytics import get_clip_stock_fields, record_final_clip
from app.services.thumbnails import make_thumbnail, WIDE_WIDTH
from app.utils.person_name import normalize_person_name




_UNSAFE_IN_FILENAME = re.compile(r"[^a-z0-9]+")


def _filename_slug(value: str, limit: int = 48) -> str:
    """
    Reduce a content type to something safe to name a file with.

    content_type is written by the model in whatever shape the channel's DNA
    invites, so it arrives as free text — one channel yields `family_story`,
    another `innuendo / host starts and refuses to finish`. A slash in that
    string reads as a path separator, so FFmpeg looks for a directory nobody
    created and reports "No such file or directory"; that took out all seven
    clips of a job at once. Long values are a quieter version of the same
    problem, since the name also becomes an R2 key.

    Only the name on disk is reduced. The stored content_type keeps the model's
    own wording, which is what the channel's analytics read.
    """
    slug = _UNSAFE_IN_FILENAME.sub("_", (value or "").lower()).strip("_")
    return slug[:limit].rstrip("_") or "clip"


def _sanity_check_word_boundary(final_start: float, final_end: float, words: list, clip_index: int) -> tuple[float, float]:
    """
    Cross-references final_start/final_end against Deepgram word timestamps.
    If final_start+0.3 (breath buffer removed) doesn't land near a word.start,
    snaps to the nearest word.start within 0.5s tolerance.
    Returns corrected (final_start, final_end).
    """
    if not words:
        return final_start, final_end

    # The breath buffer in S07 subtracts ~0.3s from word.start.
    # So final_start + 0.3 should be very close to a word.start.
    approx_word_start = final_start + 0.3
    tolerance = 0.5

    # Check if approx_word_start is near any word.start
    nearest_word_start = None
    nearest_dist = float('inf')
    for w in words:
        ws = w.get("start", 0)
        dist = abs(ws - approx_word_start)
        if dist < nearest_dist:
            nearest_dist = dist
            nearest_word_start = ws

    if nearest_dist > tolerance and nearest_word_start is not None:
        corrected_start = max(0.0, nearest_word_start - 0.3)
        print(f"[S08] Sanity check clip {clip_index+1}: final_start {final_start:.3f}s drifted {nearest_dist:.3f}s from nearest word boundary. Corrected to {corrected_start:.3f}s")
        final_start = corrected_start

    return final_start, final_end


def _encode_segment(video_path: str, start: float, duration: float, output_path: str) -> None:
    """Encodes a video segment with normalized parameters for concat compatibility."""
    cmd = ["ffmpeg", "-y"]
    if settings.FFMPEG_HWACCEL:
        cmd.extend(["-hwaccel", settings.FFMPEG_HWACCEL])
    cmd.extend([
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
    ])
    append_pipeline_video_encode_args(cmd)
    append_pipeline_audio_encode_args(cmd, has_audio=True)
    cmd.extend([
        "-movflags", "+faststart",
        "-avoid_negative_ts", "make_zero",
        "-map", "0:v:0", "-map", "0:a:0",
        output_path,
    ])
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _stitch_segments(setup_path: str, main_path: str, output_path: str, job_output_dir: str) -> None:
    """Concatenates two normalized video segments using FFmpeg concat demuxer."""
    concat_file = os.path.join(job_output_dir, f"_concat_{os.path.basename(output_path)}.txt")
    try:
        with open(concat_file, "w") as f:
            f.write(f"file '{setup_path}'\nfile '{main_path}'\n")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    finally:
        if os.path.exists(concat_file):
            os.remove(concat_file)


def _export_single_clip(
    index: int, clip: dict, job_id: str, channel_id: str, video_path: str,
    user_id: str | None, words: list, job_output_dir: str, total_clips: int,
    main_person: str | None = None,
) -> Optional[dict]:
    """Export a single clip: FFmpeg cut → R2 upload → Supabase insert. Returns clip dict or None."""
    supabase = get_client()
    output_path = None
    r2_uploaded = False
    try:
        final_start = clip.get("final_start", 0.0)
        final_duration = clip.get("final_duration_s", 0.0)
        final_end = clip.get("final_end", final_start + final_duration)

        if words:
            final_start, final_end = _sanity_check_word_boundary(final_start, final_end, words, index)
            final_duration = final_end - final_start
        content_type = clip.get("content_type", "unknown")

        if final_duration <= 0:
            print(f"[S08] Clip {index+1}: Invalid duration ({final_duration}s). Skipping.")
            return None

        output_filename = f"clip_{index:02d}_{_filename_slug(content_type)}.mp4"
        output_path = os.path.join(job_output_dir, output_filename)

        stitch_setup = clip.get("stitch_setup") or {}
        requires_stitch = bool(clip.get("requires_stitch") and stitch_setup)

        if requires_stitch:
            setup_start = float(stitch_setup.get("setup_start", 0))
            setup_end = float(stitch_setup.get("setup_end", 0))
            setup_duration = setup_end - setup_start
            if setup_duration > 0 and os.path.exists(video_path):
                setup_path = os.path.join(job_output_dir, f"_setup_{index:02d}.mp4")
                main_path = os.path.join(job_output_dir, f"_main_{index:02d}.mp4")
                try:
                    _encode_segment(video_path, setup_start, setup_duration, setup_path)
                    _encode_segment(video_path, final_start, final_duration, main_path)
                    _stitch_segments(setup_path, main_path, output_path, job_output_dir)
                    print(f"[S08] Clip {index+1}: Stitched setup ({setup_start:.1f}–{setup_end:.1f}s) + main ({final_start:.2f}–{final_end:.2f}s)")
                finally:
                    for p in [setup_path, main_path]:
                        if os.path.exists(p):
                            try:
                                os.remove(p)
                            except Exception:
                                pass
            else:
                requires_stitch = False

        if not requires_stitch:
            ffmpeg_cmd = ["ffmpeg", "-y"]
            if settings.FFMPEG_HWACCEL:
                ffmpeg_cmd.extend(["-hwaccel", settings.FFMPEG_HWACCEL])
            ffmpeg_cmd.extend([
                "-ss", str(final_start),
                "-i", video_path,
                "-t", str(final_duration),
            ])
            append_pipeline_video_encode_args(ffmpeg_cmd)
            append_pipeline_audio_encode_args(ffmpeg_cmd, has_audio=True)
            ffmpeg_cmd.extend([
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                "-map", "0:v:0",
                "-map", "0:a:0",
                output_path,
            ])
            print(f"[S08] Clip {index+1}/{total_clips}: Cutting {final_start:.2f}s + {final_duration:.1f}s [{content_type}]")
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            print(f"[S08] Error: Output missing or empty for clip {index+1}. Skipping.")
            return None

        file_url = output_path
        try:
            r2_url = upload_clip(job_id, output_filename, output_path)
            print(f"[S08] Uploaded to R2: {r2_url}")
            file_url = r2_url
            r2_uploaded = True
        except Exception as r2_err:
            print(f"[S08] R2 upload failed: {r2_err}. Clip will not be saved.")

        if not r2_uploaded:
            return None

        # Poster frame off the local cut, before the file is cleaned up. This is
        # the 16:9 source, so it is the cover a job card and a Cast Library
        # person card show; the 9:16 card thumbnail comes later, in S10, once
        # captions are burned in.
        #
        # Only the first clip needs one. Both consumers want a single cover per
        # job, so a frame per clip would be one image used and the rest dead
        # weight in R2. A failure here returns None and costs nothing but a card
        # falling back to the vertical thumbnail.
        thumbnail_wide_path = None
        if index == 0:
            thumbnail_wide_path = make_thumbnail(
                output_path,
                f"thumbnails/{job_id}/cover_wide.jpg",
                width=WIDE_WIDTH,
            )

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
            "standalone_score": clip.get("score"),
            "standalone_result": clip.get("quality_verdict"),
            "clip_strategy_role": clip.get("clip_strategy_role"),
            "posting_order": clip.get("posting_order"),
            "suggested_title": clip.get("suggested_title"),
            "suggested_description": clip.get("suggested_description"),
            "video_landscape_path": file_url,
            "file_url": file_url,
            "thumbnail_wide_path": thumbnail_wide_path,
            "is_successful": None,
            "quality_notes": clip.get("quality_notes"),
            # Who the clip is about, copied down from the job. Denormalised on
            # purpose: the Cast Library groups, filters and sorts on clips
            # alone, and a join per query cannot use one index. The stock
            # pipeline overwrites this below when it knows better.
            "main_person": main_person,
        }
        stock_fields = get_clip_stock_fields(job_id, clip.get("candidate_id"))
        if stock_fields:
            clip_data.update({k: v for k, v in stock_fields.items() if v is not None})
        clip_data = {k: v for k, v in clip_data.items() if v is not None}

        try:
            result = supabase.table("clips").insert(clip_data).execute()
            if result.data:
                clip_id = result.data[0].get("id")
                record_final_clip(job_id, clip.get("candidate_id"), clip_id, landscape_url=file_url)
                print(f"[S08] Clip {index+1} saved to DB (id: {clip_id})")
                return result.data[0]
            else:
                print(f"[S08] Warning: DB insert returned no data for clip {index+1}")
                return clip_data
        except Exception as db_err:
            print(f"[S08] DB insert error for clip {index+1}: {db_err}")
            return clip_data

    except subprocess.CalledProcessError as e:
        stderr_output = e.stderr.decode() if e.stderr else "no stderr"
        print(f"[S08] FFmpeg error for clip {index+1}: {stderr_output[-2000:]}")
        return None
    except Exception as e:
        print(f"[S08] Unexpected error for clip {index+1}: {e}")
        traceback.print_exc()
        return None
    finally:
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


def run(cut_results: list, job_id: str, channel_id: str, video_path: str,
        video_title: str = "", user_id: str | None = None,
        transcript_data: Optional[dict] = None) -> list:
    """
    Step 8: Export
    For each clip: FFmpeg frame-accurate cut + encode → R2 upload → Supabase insert.
    Clips are processed in parallel via ThreadPoolExecutor.
    """
    print(f"[S08] Starting export for {len(cut_results)} clips. Job: {job_id}")
    exported_clips = []

    words = transcript_data.get("words", []) if transcript_data else []

    # Read off the job row rather than taking it as an argument: this step also
    # runs inside Modal, where the only thing carried across is the job id.
    main_person = None
    try:
        job_row = (
            get_client().table("jobs")
            .select("metadata_subject_name").eq("id", job_id).execute()
        )
        if job_row.data:
            main_person = normalize_person_name(job_row.data[0].get("metadata_subject_name"))
    except Exception as e:
        print(f"[S08] Could not read main person for job {job_id}: {e}")

    job_output_dir = os.path.join(settings.OUTPUT_DIR, job_id)
    os.makedirs(job_output_dir, exist_ok=True)

    total = len(cut_results)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(
                _export_single_clip,
                index, clip, job_id, channel_id, video_path,
                user_id, words, job_output_dir, total, main_person,
            ): index
            for index, clip in enumerate(cut_results)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                if result:
                    exported_clips.append(result)
            except Exception as e:
                print(f"[S08] Thread error for clip {idx+1}: {e}")

    exported_clips.sort(key=lambda c: c.get("clip_index", 0))
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
