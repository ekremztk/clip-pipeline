"""
Standalone pipeline steps, callable with an API key.

The pipeline runs ten steps in order, and until now that was the only way to
reach any of them. But the steps are independent pieces of work, and often the
one you want is the only one you want: you already have a 9:16 cut from
somewhere else and you want this channel's caption style and watermark on it,
without a source video, a job, or the nine steps before it.

Each step gets its own endpoint here. The contract is the same for all of them:
send what you have, get back a URL. Where a step needs something you did not
send, it derives it — captions transcribe the clip they are handed rather than
asking for a transcript, which is what makes that step isolatable at all.

Captions are the first. Others follow the same shape.
"""

import os
import tempfile
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.config import settings
from app.middleware.api_key import require_api_key
from app.services.r2_client import get_r2_client

router = APIRouter(prefix="/v1", tags=["public-api"])

# The three templates the product actually offers. A key that could name any
# string would reach half-finished renderers nobody maintains.
ALLOWED_TEMPLATES = {"capcut_word_highlight_ii", "yellow_center", "clean"}

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # a finished vertical clip, not a source video


def _upload_source(local_path: str, request_id: str) -> str:
    """Put the caller's clip in R2 so Modal can fetch it, and return its URL."""
    key = f"api/{request_id}/source.mp4"
    r2 = get_r2_client()
    with open(local_path, "rb") as f:
        r2.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=f,
            ContentType="video/mp4",
        )
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"


@router.post("/captions")
async def burn_captions(
    video: Optional[UploadFile] = File(default=None),
    video_url: Optional[str] = Form(default=None),
    template: str = Form(default="clean"),
    channel_id: Optional[str] = Form(default=None),
    key_row: dict = Depends(require_api_key),
):
    """
    Burn captions onto one vertical clip.

    Send `video` as multipart, or `video_url` if the file is already reachable.
    `template` picks the caption style; `channel_id` decides the watermark and
    defaults to whichever channel the key acts as. A key with no channel, and
    no channel named here, produces unmarked output — marking is always
    something someone asked for.

    NOTE: synchronous. The call holds open for as long as the render takes,
    which is fine for one short clip and will not be for batches or long
    videos. When that day comes this returns a request id and grows a status
    endpoint; the response already carries `request_id` so callers written
    against this version keep working.
    """
    if not video and not video_url:
        raise HTTPException(status_code=400, detail="Send either `video` or `video_url`")
    if video and video_url:
        raise HTTPException(status_code=400, detail="Send `video` or `video_url`, not both")

    template = (template or "clean").strip()
    if template not in ALLOWED_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template. Allowed: {', '.join(sorted(ALLOWED_TEMPLATES))}",
        )

    # An explicit channel wins, then the key's own. Neither is required.
    effective_channel = (channel_id or key_row.get("channel_id") or "").replace("-", "_")
    request_id = uuid.uuid4().hex

    tmp_path = ""
    try:
        if video:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4", prefix="api_captions_") as handle:
                tmp_path = handle.name
                written = 0
                while True:
                    chunk = await video.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="Video too large")
                    handle.write(chunk)
            if not os.path.getsize(tmp_path):
                raise HTTPException(status_code=400, detail="Uploaded video is empty")
            source_url = _upload_source(tmp_path, request_id)
        else:
            source_url = video_url.strip()

        import modal as _modal
        fn = _modal.Function.from_name(settings.MODAL_GPU_APP_NAME, "caption_clip")
        result = fn.remote(
            video_url=source_url,
            request_id=request_id,
            template_key=template,
            channel_id=effective_channel or None,
        )

        return {
            "request_id": request_id,
            "captioned_url": result.get("captioned_url"),
            "thumbnail_url": result.get("thumbnail_url"),
            "word_count": result.get("word_count"),
            "language": result.get("language"),
            "template": template,
            "watermarked_as": effective_channel or None,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[PublicAPI] captions failed ({request_id}): {e}")
        raise HTTPException(status_code=500, detail=f"Captioning failed: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
