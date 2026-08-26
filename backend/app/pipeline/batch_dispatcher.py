"""
Starts queued batch jobs as slots free up.

Nothing else in the pipeline serialises anything. `POST /jobs` hands each
request straight to a background task, so N requests start N pipelines at once
— fine when a person is clicking Start once at a time, ruinous when a batch
hands over ten sources. S01-S07 run on this box, in one uvicorn process, and a
Railway container that runs out of memory takes every in-flight job with it.

So the batch endpoint writes its jobs as `queued` and starts nothing. This
loop is what moves them, and it is the only thing that does — which is what
makes `max_parallel` an actual ceiling rather than a suggestion.
"""

import asyncio
from typing import Optional

from app.services.supabase_client import get_client

# Statuses that mean a job is occupying a slot. Anything else is either
# finished or has not started, and neither holds capacity.
ACTIVE_STATUSES = ("processing", "analyzing", "cutting")

POLL_SECONDS = 10

# Never more than this, whatever a batch row asks for. The row is written by an
# API that clamps too, but a hand-edited row should not be able to melt the box.
HARD_MAX_PARALLEL = 3


def _running_count(batch_id: str) -> int:
    res = (
        get_client().table("jobs").select("id", count="exact")
        .eq("batch_id", batch_id).in_("status", list(ACTIVE_STATUSES)).execute()
    )
    return res.count or 0


def _claim_next_job(batch_id: str) -> Optional[dict]:
    """
    Take the next queued job of this batch, or None if there is nothing to take.

    The claim is the update itself, not the read before it: two dispatcher ticks
    overlapping (a slow tick, a restart mid-loop) would both see the same queued
    row, and both would start it. Filtering the update on `status='queued'` means
    the second one changes no rows and gets an empty list back, so it knows it
    lost and moves on.
    """
    nxt = (
        get_client().table("jobs")
        .select("id,batch_position")
        .eq("batch_id", batch_id).eq("status", "queued")
        .order("batch_position").limit(1).execute()
    )
    if not nxt.data:
        return None

    job_id = nxt.data[0]["id"]
    claimed = (
        get_client().table("jobs")
        .update({"status": "processing", "current_step": "starting"})
        .eq("id", job_id).eq("status", "queued").execute()
    )
    if not claimed.data:
        return None          # another tick got there first

    full = get_client().table("jobs").select("*").eq("id", job_id).execute()
    return full.data[0] if full.data else None


async def _start_job(job: dict) -> None:
    """
    Hand a claimed job to the same background path a single-job start uses.

    Everything the pipeline needs is read off the row rather than passed down
    from the request that created it, because that request finished hours ago.
    That is why `metadata_subject_name` had to become a column.
    """
    from app.api.routes.jobs import _fetch_upload_and_run_pipeline

    video_path = job.get("video_path") or ""
    if not video_path.startswith("pending_r2:"):
        # A batch only ever creates R2-backed jobs. Anything else means the row
        # was written by something other than the batch endpoint; refusing is
        # safer than guessing at a source.
        get_client().table("jobs").update({
            "status": "failed",
            "error_message": "Batch job has no R2 upload to fetch",
        }).eq("id", job["id"]).execute()
        return

    upload_id = video_path.split("pending_r2:", 1)[1]
    up = get_client().table("video_uploads").select("r2_key,filename").eq("id", upload_id).execute()
    if not up.data:
        get_client().table("jobs").update({
            "status": "failed",
            "error_message": "Source upload no longer exists",
        }).eq("id", job["id"]).execute()
        return

    import os
    ext = os.path.splitext(up.data[0].get("filename") or "")[1].lower() or ".mp4"

    await _fetch_upload_and_run_pipeline(
        job["id"],
        upload_id,
        up.data[0]["r2_key"],
        ext,
        job.get("video_title") or "Untitled",
        job.get("target_guest"),
        job.get("metadata_subject_name"),
        job["channel_id"],
        job["user_id"],
        job.get("clip_duration_min"),
        job.get("clip_duration_max"),
        job.get("trim_start_seconds") or 0.0,
        job.get("trim_end_seconds"),
    )


def _settle_if_done(batch_id: str) -> None:
    left = (
        get_client().table("jobs").select("id", count="exact")
        .eq("batch_id", batch_id)
        .in_("status", ["queued", *ACTIVE_STATUSES]).execute()
    )
    if (left.count or 0) == 0:
        get_client().table("batches").update({
            "status": "completed",
            "completed_at": "now()",
        }).eq("id", batch_id).execute()


async def _tick() -> None:
    batches = get_client().table("batches").select("id,max_parallel").eq("status", "running").execute()
    for b in batches.data or []:
        batch_id = b["id"]
        cap = min(int(b.get("max_parallel") or 1), HARD_MAX_PARALLEL)

        free = cap - _running_count(batch_id)
        for _ in range(max(0, free)):
            job = _claim_next_job(batch_id)
            if not job:
                break
            # Fire and forget: the pipeline takes minutes and the loop has other
            # batches to look at. A crash inside is caught by the task wrapper
            # below, never by this loop.
            asyncio.create_task(_run_guarded(job))

        _settle_if_done(batch_id)


async def _run_guarded(job: dict) -> None:
    try:
        await _start_job(job)
    except Exception as e:
        print(f"[BatchDispatcher] job {job.get('id')} failed to start: {e}")
        try:
            get_client().table("jobs").update({
                "status": "failed",
                "error_message": f"Batch start error: {e}",
            }).eq("id", job["id"]).execute()
        except Exception:
            pass


async def batch_dispatcher_loop() -> None:
    print("[BatchDispatcher] started")
    while True:
        try:
            await _tick()
        except Exception as e:
            # One bad batch row must not stop every other batch forever.
            print(f"[BatchDispatcher] tick error: {e}")
        await asyncio.sleep(POLL_SECONDS)
