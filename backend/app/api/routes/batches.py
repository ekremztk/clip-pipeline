"""
Batch clip runs — many sources queued once, started by the dispatcher.

The single-job endpoint in `jobs.py` starts its pipeline the moment the row
lands. A batch must not: ten sources arriving together would become ten
concurrent pipelines on one box. So this endpoint writes `queued` rows and
stops. `app/pipeline/batch_dispatcher.py` is what moves them, one free slot at
a time.
"""

import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from app.limiter import limiter
from app.middleware.auth import get_current_user
from app.middleware.roles import is_admin_user
from app.models.enums import JobStatus
from app.services.supabase_client import get_client

router = APIRouter(prefix="/batches", tags=["batches"])

MAX_SOURCES = 10

# Mirrors HARD_MAX_PARALLEL in the dispatcher. Kept in both places on purpose:
# the API refuses to store a number it cannot honour, and the dispatcher
# refuses to honour a number it did not store.
MAX_PARALLEL = 3

_ALLOWED_MODELS = ("opus-5", "opus-4-6")
_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class BatchSource(BaseModel):
    upload_id: str
    title: str
    target_guest: Optional[str] = None
    metadata_subject_name: Optional[str] = None
    clip_duration_min: Optional[int] = None
    clip_duration_max: Optional[int] = None
    caption_template: Optional[str] = None
    reframe_content_type: Optional[str] = None
    s05_model: Optional[str] = None
    s06_model: Optional[str] = None
    trim_start_seconds: float = 0.0
    trim_end_seconds: Optional[float] = None


class BatchCreateBody(BaseModel):
    channel_id: str
    name: Optional[str] = None
    max_parallel: int = 2
    sources: List[BatchSource] = Field(..., min_length=1, max_length=MAX_SOURCES)


@router.post("")
@limiter.limit("20/hour")
async def create_batch(request: Request, body: BatchCreateBody, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    # Batch is an admin tool for now. A client account can queue ten jobs whose
    # credits are only reserved when each one starts, so a batch could run half
    # way and then stall on an empty balance — that needs its own handling
    # before clients get the button.
    if not is_admin_user(user_id):
        raise HTTPException(status_code=403, detail="Batch runs are not available on this account.")

    channel_id = body.channel_id.replace("-", "_")
    supabase = get_client()

    channel = supabase.table("channels").select("id").eq("id", channel_id).eq("user_id", user_id).execute()
    if not channel.data:
        raise HTTPException(status_code=404, detail="Channel not found")

    max_parallel = max(1, min(int(body.max_parallel or 1), MAX_PARALLEL))

    # Verify every upload before writing anything. A batch that creates six rows
    # and then discovers the seventh source is missing leaves the operator to
    # clean up half a batch by hand.
    resolved = []
    for src in body.sources:
        up = (
            supabase.table("video_uploads").select("id,r2_key,filename,ready,consumed")
            .eq("id", src.upload_id).eq("user_id", user_id).execute()
        )
        if not up.data:
            raise HTTPException(status_code=404, detail=f"Upload not found: {src.upload_id}")
        row = up.data[0]
        if not row.get("ready"):
            raise HTTPException(status_code=400, detail=f"Upload still in progress: {src.title}")
        if row.get("consumed"):
            raise HTTPException(status_code=409, detail=f"Upload already used: {src.title}")
        resolved.append((src, row))

    batch = supabase.table("batches").insert({
        "user_id": user_id,
        "channel_id": channel_id,
        "name": body.name or None,
        "max_parallel": max_parallel,
        "status": "running",
    }).execute()
    if not batch.data:
        raise HTTPException(status_code=500, detail="Failed to create batch")
    batch_id = batch.data[0]["id"]

    created = []
    for position, (src, _row) in enumerate(resolved):
        job_data = {
            "channel_id": channel_id,
            "user_id": user_id,
            "video_title": src.title,
            "target_guest": src.target_guest,
            "metadata_subject_name": src.metadata_subject_name,
            "status": JobStatus.QUEUED.value,
            "current_step": "queued",
            "progress_pct": 0,
            # The dispatcher resolves this back to an upload when a slot frees.
            # Claiming `consumed` now would hold the row for hours; the existing
            # single-job claim in jobs.py happens at fetch time and this reuses it.
            "video_path": f"pending_r2:{src.upload_id}",
            "trim_start_seconds": src.trim_start_seconds,
            "trim_end_seconds": src.trim_end_seconds,
            "batch_id": batch_id,
            "batch_position": position,
        }
        if src.clip_duration_min is not None:
            job_data["clip_duration_min"] = src.clip_duration_min
        if src.clip_duration_max is not None:
            job_data["clip_duration_max"] = src.clip_duration_max
        if src.caption_template:
            job_data["caption_template"] = src.caption_template
        if src.reframe_content_type in ("podcast", "gaming"):
            job_data["reframe_content_type"] = src.reframe_content_type
        # Same admin gate as the single-job path: the selector is hidden for
        # clients, but the UI is not what enforces it.
        if src.s05_model in _ALLOWED_MODELS:
            job_data["s05_model"] = src.s05_model
        if src.s06_model in _ALLOWED_MODELS:
            job_data["s06_model"] = src.s06_model

        row = supabase.table("jobs").insert(job_data).execute()
        if row.data:
            created.append(row.data[0]["id"])

    print(f"[Batches] {batch_id}: {len(created)} jobs queued, max_parallel={max_parallel}")
    return {"batch_id": batch_id, "job_ids": created, "max_parallel": max_parallel}


@router.get("")
async def list_batches(channel_id: str, limit: int = 30, current_user: dict = Depends(get_current_user)):
    """Batches newest first, each with a per-status count of its jobs."""
    channel_id = channel_id.replace("-", "_")
    supabase = get_client()

    rows = (
        supabase.table("batches").select("*")
        .eq("channel_id", channel_id).eq("user_id", current_user["id"])
        .order("created_at", desc=True).limit(limit).execute()
    )
    batches = rows.data or []
    if not batches:
        return []

    jobs = (
        supabase.table("jobs").select("id,batch_id,status")
        .in_("batch_id", [b["id"] for b in batches]).execute()
    )
    by_batch: dict = {}
    for j in jobs.data or []:
        by_batch.setdefault(j["batch_id"], []).append(j["status"])

    for b in batches:
        statuses = by_batch.get(b["id"], [])
        b["job_count"] = len(statuses)
        b["completed_count"] = sum(1 for s in statuses if s == "completed")
        b["failed_count"] = sum(1 for s in statuses if s == "failed")
        b["queued_count"] = sum(1 for s in statuses if s == "queued")
    return batches


@router.get("/{batch_id}")
async def get_batch(batch_id: str, current_user: dict = Depends(get_current_user)):
    supabase = get_client()
    b = (
        supabase.table("batches").select("*")
        .eq("id", batch_id).eq("user_id", current_user["id"]).execute()
    )
    if not b.data:
        raise HTTPException(status_code=404, detail="Batch not found")

    jobs = (
        supabase.table("jobs").select("*")
        .eq("batch_id", batch_id).order("batch_position").execute()
    )
    rows = jobs.data or []

    # One frame per row, so the list reads as "which source is which" rather
    # than a column of near-identical filenames. Fetched here in one query
    # instead of one request per row from the browser.
    if rows:
        clips = (
            supabase.table("clips")
            .select("job_id,posting_order,video_captioned_path,video_reframed_path,file_url")
            .in_("job_id", [j["id"] for j in rows])
            .order("posting_order")
            .execute()
        )
        first_by_job: dict = {}
        for c in clips.data or []:
            url = c.get("video_captioned_path") or c.get("video_reframed_path") or c.get("file_url")
            if url and c["job_id"] not in first_by_job:
                first_by_job[c["job_id"]] = url
        for j in rows:
            j["thumb_url"] = first_by_job.get(j["id"])

    return {"batch": b.data[0], "jobs": rows}


@router.delete("/{batch_id}")
async def cancel_batch(batch_id: str, current_user: dict = Depends(get_current_user)):
    """
    Stop a batch from starting anything further.

    Jobs already running are left alone — killing a pipeline mid-flight would
    strand its R2 objects and its reserved credits. Only the queue is cleared.
    """
    supabase = get_client()
    b = supabase.table("batches").select("id").eq("id", batch_id).eq("user_id", current_user["id"]).execute()
    if not b.data:
        raise HTTPException(status_code=404, detail="Batch not found")

    supabase.table("batches").update({"status": "cancelled"}).eq("id", batch_id).execute()
    cancelled = (
        supabase.table("jobs")
        .update({"status": "failed", "error_message": "Batch cancelled"})
        .eq("batch_id", batch_id).eq("status", "queued").execute()
    )
    return {"ok": True, "cancelled_jobs": len(cancelled.data or [])}
