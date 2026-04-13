"""
Debug endpoint — S09 reframe test.

POST /debug/reframe-test
  Body: { "clip_url": "https://..." }
  Returns: { "reframed_url": "https://r2.../...", "metadata": {...} }

Runs exactly what S09 does for podcast reframe.
Remove this file when testing is done.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/debug", tags=["debug"])


class ReframeTestRequest(BaseModel):
    clip_url: str


@router.post("/reframe-test")
def reframe_test(req: ReframeTestRequest):
    from app.pipeline.steps.s09_reframe import _reframe_podcast

    if not req.clip_url:
        raise HTTPException(status_code=400, detail="clip_url required")

    try:
        reframed_url, metadata = _reframe_podcast(
            clip_url=req.clip_url,
            job_id="",
            clip_index=0,
        )
        return {"reframed_url": reframed_url, "metadata": metadata}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
