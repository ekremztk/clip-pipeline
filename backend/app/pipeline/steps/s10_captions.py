"""
Step 10: Auto Captions
For each reframed 9:16 clip: transcribe with Deepgram → burn captions via FFmpeg.

Uses the caption template from channel_dna (defaults to "clean").
Result: video_captioned_path updated on each clip row.
"""
import logging
import os
import traceback
import uuid

from app.config import settings
from app.services.supabase_client import get_client
from app.services.r2_client import get_r2_client
from app.captions.core import transcribe_video
from app.captions.renderer import render_captions

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
    supabase = get_client()
    captioned_clips = []

    def _process_clip(index: int, clip: dict) -> tuple[int, dict]:
        clip_id = clip.get("id")

        # Merged mode: S09 produced a filter chain instead of a rendered file.
        # Input is the landscape cut from S08; vf prepends crop+scale before captions.
        reframe_filter_chain = clip.get("reframe_filter_chain")
        local_source_path = clip.get("local_source_path")

        if reframe_filter_chain and local_source_path:
            clip_url = clip.get("video_landscape_path") or clip.get("file_url")
            local_hint = local_source_path
            prepend_vf = reframe_filter_chain
            merged_mode = True
        else:
            # Legacy / gaming path: S09 rendered a 9:16 file.
            clip_url = clip.get("video_reframed_path")
            local_hint = clip.get("local_reframed_path")
            prepend_vf = None
            merged_mode = False

        if not clip_url and not local_hint:
            print(f"[S10] Clip {index+1}: No reframed/landscape source. Skipping captions.")
            return index, clip

        try:
            captioned_url, caption_meta = _caption_clip(
                clip_url=clip_url,
                clip_index=index,
                template_key=caption_template,
                local_path_hint=local_hint,
                prepend_vf=prepend_vf,
            )

            db_update = {
                "video_captioned_path": captioned_url,
                "caption_metadata": caption_meta,
            }
            if merged_mode:
                # Reframe+captions collapsed into one pass — the captioned MP4 is
                # also the definitive 9:16 output, so align video_reframed_path
                # with the captioned URL.
                db_update["video_reframed_path"] = captioned_url

            if clip_id and captioned_url:
                try:
                    supabase.table("clips").update(db_update).eq("id", str(clip_id)).execute()
                    print(f"[S10] Clip {index+1} (id: {clip_id}) captioned: {captioned_url}")
                except Exception as db_err:
                    print(f"[S10] DB update error for clip {index+1}: {db_err}")

            out = {**clip, "video_captioned_path": captioned_url, "caption_metadata": caption_meta}
            if merged_mode:
                out["video_reframed_path"] = captioned_url
            return index, out

        except Exception as e:
            print(f"[S10] Caption error for clip {index+1}: {e}")
            traceback.print_exc()
            return index, clip

    for index, clip in enumerate(reframed_clips):
        try:
            result_idx, result_clip = _process_clip(index, clip)
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


def _caption_clip(
    clip_url: str | None,
    clip_index: int,
    template_key: str,
    local_path_hint: str | None = None,
    prepend_vf: str | None = None,
) -> tuple[str, dict]:
    """
    Transcribe a clip and burn captions:
    1. Use local path if provided (from S08 landscape or S09 reframed), else download
    2. Deepgram transcription → words + segments
    3. render_captions() → captioned MP4 (with optional prepend_vf for merged reframe+caption pass)
    4. Upload to R2

    Returns (captioned_r2_url, caption_metadata)
    """
    import requests

    print(f"[S10] Captioning clip {clip_index+1}: {clip_url or local_path_hint}")

    downloaded = False
    upload_dir = str(settings.UPLOAD_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    output_path = os.path.join(upload_dir, f"s10_captioned_{uuid.uuid4().hex}.mp4")

    if local_path_hint and os.path.exists(local_path_hint):
        local_path = local_path_hint
        print(f"[S10] Clip {clip_index+1}: using local source (skipping download)")
    else:
        if not clip_url:
            raise RuntimeError(f"[S10] Clip {clip_index+1}: no local path and no URL")
        local_path = os.path.join(upload_dir, f"s10_dl_{uuid.uuid4().hex}.mp4")
        downloaded = True
        resp = requests.get(clip_url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)

    try:
        transcription = transcribe_video(local_path, language=None)
        words = transcription["words"]
        segments = transcription["segments"]
        transcript_text = transcription["text"]
        detected_language = transcription["language"]

        print(f"[S10] Clip {clip_index+1}: {len(words)} words, {len(segments)} segments, lang={detected_language}")

        render_captions(
            video_path=local_path,
            output_path=output_path,
            words=words,
            segments=segments,
            template_key=template_key,
            prepend_vf=prepend_vf,
        )

        r2_url = _upload_to_r2(output_path, f"captions/{uuid.uuid4().hex}.mp4")

        caption_meta = {
            "template": template_key,
            "word_count": len(words),
            "segment_count": len(segments),
            "language": detected_language,
            "text": transcript_text[:500] if transcript_text else "",
            "words": words,
            "merged_reframe": bool(prepend_vf),
        }

        return r2_url, caption_meta

    finally:
        # Only remove files this function created. Local source paths owned by
        # S08 (landscape) or S09 (reframed) are cleaned up later by modal_app.
        if downloaded and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


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
