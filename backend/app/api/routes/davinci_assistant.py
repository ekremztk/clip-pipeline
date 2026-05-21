from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Header, HTTPException, UploadFile, File

from app.davinci.assistant import analyze_clip


router = APIRouter(prefix="/davinci-assistant", tags=["davinci-assistant"])


def _verify_key(api_key: str | None) -> None:
    expected = os.getenv("DAVINCI_ASSISTANT_API_KEY", "").strip()
    if expected and api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid DaVinci assistant API key")


@router.post("/analyze")
async def analyze_davinci_clip(
    video: UploadFile = File(...),
    x_prognot_davinci_key: str | None = Header(default=None),
):
    _verify_key(x_prognot_davinci_key)
    tmp_video = ""
    try:
        suffix = ".mov" if (video.filename or "").lower().endswith(".mov") else ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="davinci_assistant_") as handle:
            tmp_video = handle.name
            while True:
                chunk = await video.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        if not os.path.exists(tmp_video) or os.path.getsize(tmp_video) == 0:
            raise HTTPException(status_code=400, detail="Uploaded video is empty")
        return analyze_clip(tmp_video)
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[DaVinciAssistantRoute] Error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if tmp_video and os.path.exists(tmp_video):
            try:
                os.remove(tmp_video)
            except Exception:
                pass
