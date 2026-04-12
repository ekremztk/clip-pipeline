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

    for index, clip in enumerate(reframed_clips):
        clip_id = clip.get("id")
        reframed_url = clip.get("video_reframed_path")

        if not reframed_url:
            print(f"[S10] Clip {index+1}: No video_reframed_path. Skipping captions.")
            captioned_clips.append(clip)
            continue

        captioned_url = None
        caption_meta = {}

        try:
            captioned_url, caption_meta = _caption_clip(
                clip_url=reframed_url,
                clip_index=index,
                template_key=caption_template,
            )

            # Update clip row in Supabase
            if clip_id and captioned_url:
                try:
                    supabase.table("clips").update({
                        "video_captioned_path": captioned_url,
                        "caption_metadata": caption_meta,
                    }).eq("id", str(clip_id)).execute()
                    print(f"[S10] Clip {index+1} (id: {clip_id}) captioned: {captioned_url}")
                except Exception as db_err:
                    print(f"[S10] DB update error for clip {index+1}: {db_err}")

            updated_clip = {**clip, "video_captioned_path": captioned_url, "caption_metadata": caption_meta}
            captioned_clips.append(updated_clip)

        except Exception as e:
            print(f"[S10] Caption error for clip {index+1}: {e}")
            traceback.print_exc()
            captioned_clips.append(clip)

    successful = sum(1 for c in captioned_clips if c.get("video_captioned_path"))
    print(f"[S10] Captions complete. {successful}/{len(reframed_clips)} clips captioned.")
    return captioned_clips


def _caption_clip(
    clip_url: str,
    clip_index: int,
    template_key: str,
) -> tuple[str, dict]:
    """
    Transcribe a clip and burn captions:
    1. Download clip to temp
    2. Deepgram transcription → words + segments
    3. render_captions() → captioned MP4
    4. Upload to R2

    Returns (captioned_r2_url, caption_metadata)
    """
    import requests

    print(f"[S10] Captioning clip {clip_index+1}: {clip_url}")

    # Download clip to temp
    local_path = os.path.join(str(settings.UPLOAD_DIR), f"s10_dl_{uuid.uuid4().hex}.mp4")
    output_path = os.path.join(str(settings.UPLOAD_DIR), f"s10_captioned_{uuid.uuid4().hex}.mp4")

    try:
        resp = requests.get(clip_url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)

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
        )

        # Upload to R2
        r2_url = _upload_to_r2(output_path, f"captions/{uuid.uuid4().hex}.mp4")

        caption_meta = {
            "template": template_key,
            "word_count": len(words),
            "segment_count": len(segments),
            "language": detected_language,
            "text": transcript_text[:500] if transcript_text else "",
            "words": words,   # full word list stored for "Open in Editor" replay
        }

        return r2_url, caption_meta

    finally:
        for path in [local_path, output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
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
