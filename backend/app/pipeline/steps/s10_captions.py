"""
Step 10: Auto Captions
For each reframed 9:16 clip: transcribe with Deepgram → burn captions via FFmpeg.

The caption template comes from the job row, not from channel_dna — it is a
form field on POST /jobs that the orchestrator reads back (defaults to "clean").
Result: video_captioned_path updated on each clip row.
"""
import logging
import json
import os
import subprocess
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config import settings
from app.pipeline.stock_analytics import record_candidate_stage
from app.services.supabase_client import get_client
from app.services.r2_client import get_r2_client
from app.captions.core import transcribe_video
from app.captions.renderer import render_captions
from app.captions.watermark import fetch_watermark, resolve_channel_watermark_key
from app.ffmpeg_encode import describe_pipeline_encode_profile

logger = logging.getLogger(__name__)


def run(
    reframed_clips: list,
    job_id: str,
    channel_id: str,
    caption_template: str = "clean",
) -> list:
    """
    Step 10: Auto Captions — transcribes and burns captions onto each reframed clip.

    Args:
        reframed_clips: List of clip dicts from S09 (must have video_reframed_path and id)
        job_id: Pipeline job ID
        channel_id: Channel ID
        caption_template: pipelineKey from caption-templates.ts (e.g. "clean", "hormozi")

    Returns: List of updated clip dicts with video_captioned_path set.
    """
    print(f"[S10] Starting captions for {len(reframed_clips)} clips. Template: {caption_template}")
    print(f"[S10] Pipeline encode profile: {describe_pipeline_encode_profile()}")
    supabase = get_client()
    captioned_clips = []

    # The channel owns the watermark. Never the caption template — that is a
    # style, and the default one is shared with client accounts, so deriving the
    # mark from it stamped our channel onto their videos. Resolved once per job;
    # a channel with no key set, which is every channel by default, yields None
    # and an unmarked clip. Every failure inside these two calls also yields
    # None, so the only way to mark a clip is for someone to have said so.
    watermark_path = fetch_watermark(
        resolve_channel_watermark_key(channel_id), str(settings.UPLOAD_DIR)
    )
    print(f"[S10] Watermark for channel {channel_id}: {watermark_path or 'none'}")

    def _process_clip(index: int, clip: dict) -> tuple[int, dict]:
        clip_id = clip.get("id")
        reframed_url = clip.get("video_reframed_path")

        if not reframed_url:
            print(f"[S10] Clip {index+1}: No video_reframed_path. Skipping captions.")
            record_candidate_stage(clip_id, "s10", "skipped", error_message="No video_reframed_path")
            return index, clip

        local_hint = clip.get("local_reframed_path")

        try:
            captioned_url, caption_meta = _caption_clip(
                clip_url=reframed_url,
                clip_index=index,
                template_key=caption_template,
                local_path_hint=local_hint,
                watermark_path=watermark_path,
            )

            if clip_id and captioned_url:
                try:
                    supabase.table("clips").update({
                        "video_captioned_path": captioned_url,
                        "caption_metadata": caption_meta,
                    }).eq("id", str(clip_id)).execute()
                    print(f"[S10] Clip {index+1} (id: {clip_id}) captioned: {captioned_url}")
                except Exception as db_err:
                    print(f"[S10] DB update error for clip {index+1}: {db_err}")
                record_candidate_stage(clip_id, "s10", "completed", url=captioned_url)

            return index, {**clip, "video_captioned_path": captioned_url, "caption_metadata": caption_meta}

        except Exception as e:
            print(f"[S10] Caption error for clip {index+1}: {e}")
            traceback.print_exc()
            record_candidate_stage(clip_id, "s10", "failed", error_message=str(e))
            return index, clip

    try:
        max_workers = min(3, max(1, len(reframed_clips)))
        print(f"[S10] Caption worker pool: max_workers={max_workers}")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_process_clip, index, clip): (index, clip)
                for index, clip in enumerate(reframed_clips)
            }
            for future in as_completed(futures):
                index, clip = futures[future]
                try:
                    result_idx, result_clip = future.result()
                    captioned_clips.append((result_idx, result_clip))
                except Exception as e:
                    print(f"[S10] Caption error for clip {index+1}: {e}")
                    traceback.print_exc()
                    captioned_clips.append((index, clip))

        captioned_clips.sort(key=lambda x: x[0])
        captioned_clips = [clip for _, clip in captioned_clips]

        successful = sum(1 for c in captioned_clips if c.get("video_captioned_path"))
        print(f"[S10] Captions complete. {successful}/{len(reframed_clips)} clips captioned.")
        return captioned_clips
    finally:
        if watermark_path and os.path.exists(watermark_path):
            try:
                os.remove(watermark_path)
            except Exception:
                pass


def _caption_clip(
    clip_url: str,
    clip_index: int,
    template_key: str,
    local_path_hint: str | None = None,
    watermark_path: str | None = None,
) -> tuple[str, dict]:
    """
    Transcribe a clip and burn captions:
    1. Use local path from S09 if available, otherwise download from R2
    2. Deepgram transcription → words + segments
    3. render_captions() → captioned MP4
    4. Upload to R2

    Returns (captioned_r2_url, caption_metadata)
    """
    import requests

    print(f"[S10] Captioning clip {clip_index+1}: {clip_url}")

    downloaded = False
    upload_dir = str(settings.UPLOAD_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    output_path = os.path.join(upload_dir, f"s10_captioned_{uuid.uuid4().hex}.mp4")

    if local_path_hint and os.path.exists(local_path_hint):
        local_path = local_path_hint
        print(f"[S10] Clip {clip_index+1}: using local path from S09 (skipping download)")
    else:
        local_path = os.path.join(upload_dir, f"s10_dl_{uuid.uuid4().hex}.mp4")
        downloaded = True
        resp = requests.get(clip_url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)

    try:
        # Transcribe
        transcription = transcribe_video(local_path, language=None)
        words = transcription["words"]
        segments = transcription["segments"]
        transcript_text = transcription["text"]
        detected_language = transcription["language"]

        print(f"[S10] Clip {clip_index+1}: {len(words)} words, {len(segments)} segments, lang={detected_language}")

        # Burn captions
        render_captions(
            video_path=local_path,
            output_path=output_path,
            words=words,
            segments=segments,
            template_key=template_key,
            watermark_path=watermark_path,
        )
        output_stats = _probe_caption_output(output_path)
        if output_stats:
            print(
                f"[S10] Clip {clip_index+1}: output size={output_stats.get('size_mb', 0):.1f}MB, "
                f"video_bitrate={output_stats.get('video_bitrate_mbps', 0):.2f}Mbps"
            )
            min_bitrate = int(os.getenv("FFMPEG_MIN_ACCEPTABLE_VIDEO_BITRATE", "5000000"))
            video_bitrate = output_stats.get("video_bitrate_bps")
            if video_bitrate and video_bitrate < min_bitrate:
                raise RuntimeError(
                    f"S10 output bitrate too low: {video_bitrate}bps < {min_bitrate}bps"
                )
        finalizer_meta = _finalize_caption_output(output_path)

        # Upload to R2
        r2_url = _upload_to_r2(output_path, f"captions/{uuid.uuid4().hex}.mp4")

        caption_meta = {
            "template": template_key,
            "word_count": len(words),
            "segment_count": len(segments),
            "language": detected_language,
            "text": transcript_text[:500] if transcript_text else "",
            "words": words,   # full word list stored for "Open in Editor" replay
            "finalizer": finalizer_meta,
            "output_stats": output_stats,
        }

        return r2_url, caption_meta

    finally:
        for path in [local_path, output_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


def _probe_caption_output(path: str) -> dict:
    """Return output size and bitrate stats for S10 quality checks."""
    try:
        size_bytes = os.path.getsize(path)
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=bit_rate",
            "-show_entries", "format=bit_rate",
            "-of", "json",
            path,
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout or "{}")
        streams = data.get("streams") or []
        video_bitrate = None
        if streams:
            raw = streams[0].get("bit_rate")
            if raw:
                video_bitrate = int(raw)
        format_bitrate = None
        raw_format = (data.get("format") or {}).get("bit_rate")
        if raw_format:
            format_bitrate = int(raw_format)
        return {
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "video_bitrate_bps": video_bitrate,
            "video_bitrate_mbps": round(video_bitrate / 1_000_000, 3) if video_bitrate else 0,
            "format_bitrate_bps": format_bitrate,
        }
    except Exception as e:
        print(f"[S10] Output bitrate probe failed: {e}")
        return {}


def _upload_to_r2(local_path: str, r2_key: str) -> str:
    """Upload a local file to R2 and return the public URL."""
    r2 = get_r2_client()
    with open(local_path, "rb") as f:
        r2.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=r2_key,
            Body=f,
            ContentType="video/mp4",
        )
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{r2_key}"


def _finalize_caption_output(output_path: str) -> dict:
    """Keep S10 focused on captions; final delivery metadata is handled outside the pipeline."""
    del output_path
    return {"skipped": True, "reason": "pipeline_encode_only"}
