from __future__ import annotations

import os
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.middleware.auth import get_current_user
from app.models.enums import JobStatus
from app.pipeline.orchestrator import run_pipeline, update_job
from app.services.r2_client import download_r2_to_local
from app.services.supabase_client import get_client, get_db_url


router = APIRouter(prefix="/stock-worker", tags=["stock-worker"])


class StockQueueItem(BaseModel):
    source_url: str
    r2_key: Optional[str] = None
    video_title: str
    main_person: str
    series: Optional[str] = None
    target_guest: Optional[str] = None
    caption_template: str = "clean"
    reframe_content_type: str = "podcast"
    clip_duration_min: int = 10
    clip_duration_max: int = 60
    priority: int = 100


class StockEnqueueBody(BaseModel):
    channel_id: str
    batch_id: str
    clear_queued: bool = False
    items: list[StockQueueItem] = Field(default_factory=list)


class StockStartBody(BaseModel):
    channel_id: str
    batch_id: Optional[str] = None
    limit: int = Field(default=1, ge=1, le=100)
    concurrency: int = Field(default=5, ge=1, le=10)
    stagger_seconds: int = Field(default=0, ge=0, le=1800)


def _normalize_channel_id(channel_id: str) -> str:
    return channel_id.replace("-", "_").strip()


def _db_connect():
    db_url = get_db_url()
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)


def _ensure_channel_owner(channel_id: str, user_id: str) -> None:
    supabase = get_client()
    row = (
        supabase.table("channels")
        .select("id")
        .eq("id", channel_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="Channel not found")


def _clear_queued(channel_id: str, user_id: str, batch_id: str) -> int:
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM stock_pipeline_queue
                WHERE channel_id = %s
                  AND user_id = %s
                  AND batch_id = %s
                  AND status = 'queued'
                """,
                (channel_id, user_id, batch_id),
            )
            return int(cur.rowcount or 0)


def _insert_items(channel_id: str, user_id: str, batch_id: str, items: list[StockQueueItem]) -> int:
    rows = []
    for item in items:
        video_title = item.video_title.strip()
        main_person = item.main_person.strip()
        source_url = item.source_url.strip()
        if not video_title or not main_person or not source_url:
            raise HTTPException(status_code=400, detail="source_url, video_title and main_person are required")
        rows.append(
            (
                channel_id,
                user_id,
                batch_id,
                item.series,
                source_url,
                item.r2_key,
                video_title,
                main_person,
                item.target_guest.strip() if item.target_guest and item.target_guest.strip() else None,
                item.caption_template or "clean",
                item.reframe_content_type or "podcast",
                item.clip_duration_min,
                item.clip_duration_max,
                item.priority,
            )
        )

    if not rows:
        return 0

    with _db_connect() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO stock_pipeline_queue (
                    channel_id, user_id, batch_id, series, source_url, r2_key,
                    video_title, main_person, target_guest, caption_template,
                    reframe_content_type, clip_duration_min, clip_duration_max, priority
                ) VALUES %s
                ON CONFLICT (channel_id, batch_id, source_url)
                DO UPDATE SET
                    series = EXCLUDED.series,
                    r2_key = EXCLUDED.r2_key,
                    video_title = EXCLUDED.video_title,
                    main_person = EXCLUDED.main_person,
                    target_guest = EXCLUDED.target_guest,
                    caption_template = EXCLUDED.caption_template,
                    reframe_content_type = EXCLUDED.reframe_content_type,
                    clip_duration_min = EXCLUDED.clip_duration_min,
                    clip_duration_max = EXCLUDED.clip_duration_max,
                    priority = EXCLUDED.priority,
                    updated_at = now()
                WHERE stock_pipeline_queue.status IN ('queued', 'failed')
                """,
                rows,
            )
            return len(rows)


def _claim_next_item(channel_id: str, user_id: str, batch_id: Optional[str]) -> Optional[dict]:
    batch_filter = "AND batch_id = %s" if batch_id else ""
    params: list[object] = [channel_id, user_id]
    if batch_id:
        params.append(batch_id)

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH next_item AS (
                    SELECT id
                    FROM stock_pipeline_queue
                    WHERE channel_id = %s
                      AND user_id = %s
                      AND status = 'queued'
                      {batch_filter}
                    ORDER BY priority ASC, created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE stock_pipeline_queue q
                SET status = 'processing',
                    locked_at = now(),
                    started_at = COALESCE(started_at, now()),
                    attempt_count = q.attempt_count + 1,
                    updated_at = now()
                FROM next_item
                WHERE q.id = next_item.id
                RETURNING q.*
                """,
                params,
            )
            row = cur.fetchone()
            return dict(row) if row else None


def _mark_queue_item(item_id: str, status: str, error_message: Optional[str] = None, job_id: Optional[str] = None) -> None:
    payload = {
        "status": status,
        "error_message": error_message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if job_id:
        payload["job_id"] = job_id
    if status in {"completed", "failed"}:
        payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    get_client().table("stock_pipeline_queue").update(payload).eq("id", item_id).execute()


def _download_stock_source(item: dict, job_id: str) -> str:
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    local_path = str(Path(settings.UPLOAD_DIR) / f"{job_id}.mp4")

    r2_key = item.get("r2_key")
    if r2_key:
        print(f"[StockWorker] Downloading R2 source {r2_key} -> {local_path}")
        download_r2_to_local(r2_key, local_path)
        return local_path

    source_url = item["source_url"]
    print(f"[StockWorker] Downloading source URL -> {local_path}")
    with httpx.stream("GET", source_url, timeout=600.0, follow_redirects=True) as response:
        response.raise_for_status()
        with open(local_path, "wb") as handle:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return local_path


def _create_job_for_item(item: dict) -> str:
    job_id = str(uuid.uuid4())
    job_data = {
        "id": job_id,
        "channel_id": item["channel_id"],
        "user_id": item["user_id"],
        "video_title": item["video_title"],
        "target_guest": item.get("target_guest"),
        "status": JobStatus.QUEUED.value,
        "current_step": "queued",
        "progress_pct": 0,
        "video_path": f"stock_queue:{item['id']}",
        "clip_duration_min": item.get("clip_duration_min") or 10,
        "clip_duration_max": item.get("clip_duration_max") or 60,
        "reframe_content_type": item.get("reframe_content_type") or "podcast",
        "caption_template": item.get("caption_template") or "clean",
    }
    response = get_client().table("jobs").insert(job_data).execute()
    if not response.data:
        raise RuntimeError("Failed to create job")
    return job_id


def _run_one_item(item: dict) -> None:
    item_id = str(item["id"])
    job_id = ""
    video_path = ""
    try:
        job_id = _create_job_for_item(item)
        _mark_queue_item(item_id, "processing", job_id=job_id)
        video_path = _download_stock_source(item, job_id)
        get_client().table("jobs").update({"video_path": video_path}).eq("id", job_id).execute()

        run_pipeline(
            job_id=job_id,
            video_path=video_path,
            video_title=item["video_title"],
            target_guest=item.get("target_guest"),
            channel_id=item["channel_id"],
            user_id=item["user_id"],
            clip_duration_min=item.get("clip_duration_min") or 10,
            clip_duration_max=item.get("clip_duration_max") or 60,
            metadata_subject_name=item["main_person"],
        )

        job = (
            get_client().table("jobs")
            .select("status,error_message")
            .eq("id", job_id)
            .limit(1)
            .execute()
        )
        job_status = (job.data or [{}])[0].get("status")
        if job_status == JobStatus.FAILED.value:
            error = (job.data or [{}])[0].get("error_message") or "Pipeline failed"
            _mark_queue_item(item_id, "failed", error_message=error, job_id=job_id)
        else:
            _mark_queue_item(item_id, "completed", job_id=job_id)
    except Exception as exc:
        print(f"[StockWorker] Item {item_id} failed: {exc}")
        if job_id:
            update_job(job_id, status=JobStatus.FAILED.value, error_message=str(exc))
        _mark_queue_item(item_id, "failed", error_message=str(exc), job_id=job_id or None)
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except Exception:
                pass


def run_stock_worker(channel_id: str, user_id: str, batch_id: Optional[str], limit: int) -> None:
    processed = 0
    print(f"[StockWorker] Starting channel={channel_id} batch={batch_id or '*'} limit={limit}")
    while processed < limit:
        item = _claim_next_item(channel_id, user_id, batch_id)
        if not item:
            print("[StockWorker] No queued items left")
            break
        print(
            f"[StockWorker] Claimed item={item['id']} title='{item['video_title']}' "
            f"main_person='{item['main_person']}'"
        )
        _run_one_item(item)
        processed += 1
    print(f"[StockWorker] Finished processed={processed}")


def _run_claimed_worker_slot(channel_id: str, user_id: str, batch_id: Optional[str], slot: int) -> bool:
    item = _claim_next_item(channel_id, user_id, batch_id)
    if not item:
        print(f"[StockWorker] Slot {slot}: no queued item left")
        return False
    print(
        f"[StockWorker] Slot {slot}: claimed item={item['id']} title='{item['video_title']}' "
        f"main_person='{item['main_person']}'"
    )
    _run_one_item(item)
    return True


def run_stock_worker_staggered(
    channel_id: str,
    user_id: str,
    batch_id: Optional[str],
    limit: int,
    concurrency: int,
    stagger_seconds: int,
) -> None:
    if concurrency <= 1:
        run_stock_worker(channel_id, user_id, batch_id, limit)
        return

    started = 0
    max_workers = min(concurrency, limit)
    active: dict[Future, str] = {}
    print(
        f"[StockWorker] Starting pool channel={channel_id} batch={batch_id or '*'} "
        f"limit={limit} concurrency={max_workers}"
    )
    if stagger_seconds > 0:
        print("[StockWorker] stagger_seconds is ignored by pool mode; slots refill immediately")

    def submit_next(executor: ThreadPoolExecutor) -> bool:
        nonlocal started
        if started >= limit:
            return False
        item = _claim_next_item(channel_id, user_id, batch_id)
        if not item:
            return False
        started += 1
        item_id = str(item["id"])
        print(
            f"[StockWorker] Slot start {started}/{limit}: item={item_id} "
            f"title='{item['video_title']}' main_person='{item['main_person']}'"
        )
        future = executor.submit(_run_one_item, item)
        active[future] = item_id
        return True

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while len(active) < max_workers and submit_next(executor):
            pass

        completed = 0
        while active:
            done, _ = wait(active.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                item_id = active.pop(future)
                completed += 1
                try:
                    future.result()
                except Exception as exc:
                    print(f"[StockWorker] Slot item={item_id} failed unexpectedly: {exc}")

            while len(active) < max_workers and started < limit:
                if not submit_next(executor):
                    break

    print(f"[StockWorker] Pool finished started={started} completed={completed}")


@router.post("/enqueue")
async def enqueue_stock_items(body: StockEnqueueBody, current_user: dict = Depends(get_current_user)):
    channel_id = _normalize_channel_id(body.channel_id)
    _ensure_channel_owner(channel_id, current_user["id"])
    if not body.items:
        raise HTTPException(status_code=400, detail="items must not be empty")

    cleared = _clear_queued(channel_id, current_user["id"], body.batch_id) if body.clear_queued else 0
    inserted = _insert_items(channel_id, current_user["id"], body.batch_id, body.items)
    return {"ok": True, "inserted": inserted, "cleared": cleared, "batch_id": body.batch_id}


@router.post("/start")
async def start_stock_worker(
    body: StockStartBody,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    channel_id = _normalize_channel_id(body.channel_id)
    _ensure_channel_owner(channel_id, current_user["id"])
    background_tasks.add_task(
        run_stock_worker_staggered,
        channel_id,
        current_user["id"],
        body.batch_id,
        body.limit,
        body.concurrency,
        body.stagger_seconds,
    )
    return {
        "ok": True,
        "status": "started",
        "channel_id": channel_id,
        "batch_id": body.batch_id,
        "limit": body.limit,
        "concurrency": body.concurrency,
        "stagger_seconds": body.stagger_seconds,
    }


@router.get("/items")
async def list_stock_items(
    channel_id: str,
    batch_id: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    channel_id = _normalize_channel_id(channel_id)
    _ensure_channel_owner(channel_id, current_user["id"])
    query = (
        get_client().table("stock_pipeline_queue")
        .select("*")
        .eq("channel_id", channel_id)
        .eq("user_id", current_user["id"])
        .order("created_at", desc=False)
        .limit(max(1, min(limit, 500)))
    )
    if batch_id:
        query = query.eq("batch_id", batch_id)
    response = query.execute()
    return response.data or []
