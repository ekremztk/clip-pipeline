from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.studio.analyzer import analyze_clip


router = APIRouter(prefix="/studio", tags=["studio"])


@router.post("/analyze")
async def analyze_studio_clip(
    video: UploadFile = File(...),
):
    tmp_video = ""
    try:
        ext = os.path.splitext(video.filename or "video.mp4")[1] or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="studio_") as handle:
            tmp_video = handle.name
            while True:
                chunk = await video.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)

        if not os.path.exists(tmp_video) or os.path.getsize(tmp_video) == 0:
            raise HTTPException(status_code=400, detail="Uploaded video is empty")

        result = analyze_clip(tmp_video)
        return result

    except HTTPException:
        raise
    except Exception as exc:
        print(f"[StudioRoute] Error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if tmp_video and os.path.exists(tmp_video):
            try:
                os.remove(tmp_video)
            except Exception:
                pass
