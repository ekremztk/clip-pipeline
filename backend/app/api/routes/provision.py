from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import unquote, urlparse

import psycopg2
from psycopg2.extras import Json, RealDictCursor, execute_values
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.middleware.auth import get_current_user
from app.provision.runner import run_provision_job
from app.services.r2_client import generate_presigned_download
from app.services.supabase_client import get_client, get_db_url


router = APIRouter(prefix="/provision", tags=["provision"])

DEFAULT_VARIANT_MODES = ["conservative", "tight", "loop"]
ALLOWED_VARIANT_MODES = {"conservative", "tight", "aggressive", "loop"}
ALLOWED_REVIEW_STATUSES = {"unreviewed", "selected", "rejected", "manual_fix", "posted"}


class ProvisionItemInput(BaseModel):
    clip_id: Optional[str] = None
    input_video_url: Optional[str] = None
    input_title: Optional[str] = None
    input_description: Optional[str] = None
    main_person: Optional[str] = None


class ProvisionJobCreate(BaseModel):
    channel_id: str
    name: Optional[str] = None
    variant_modes: list[str] = Field(default_factory=lambda: DEFAULT_VARIANT_MODES.copy())
    settings: dict[str, Any] = Field(default_factory=dict)
    clip_ids: list[str] = Field(default_factory=list)
    items: list[ProvisionItemInput] = Field(default_factory=list)


class ProvisionJobUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    variant_modes: Optional[list[str]] = None
    settings: Optional[dict[str, Any]] = None


class ProvisionVariantReview(BaseModel):
    review_status: str
    feedback_note: Optional[str] = None


class ProvisionJobStart(BaseModel):
    limit: int = Field(default=1, ge=1, le=20)


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


def _normalize_variant_modes(modes: list[str]) -> list[str]:
    normalized: list[str] = []
    for mode in modes or DEFAULT_VARIANT_MODES:
        value = (mode or "").strip().lower()
        if value not in ALLOWED_VARIANT_MODES:
            raise HTTPException(status_code=400, detail=f"Invalid variant mode: {mode}")
        if value not in normalized:
            normalized.append(value)
    return normalized or DEFAULT_VARIANT_MODES.copy()


def _verify_job_owner(job_id: str, user_id: str) -> dict:
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM provision_jobs
                WHERE id = %s
                  AND user_id = %s
                LIMIT 1
                """,
                (job_id, user_id),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Provision job not found")
    return dict(row)


def _fetch_clip_inputs(clip_ids: list[str], channel_id: str, user_id: str) -> list[dict]:
    if not clip_ids:
        return []
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.id AS clip_id,
                    COALESCE(c.video_captioned_path, c.video_reframed_path, c.file_url) AS input_video_url,
                    c.suggested_title AS input_title,
                    c.suggested_description AS input_description,
                    c.main_person,
                    c.channel_id,
                    j.user_id AS job_user_id
                FROM clips c
                LEFT JOIN jobs j ON j.id = c.job_id
                WHERE c.id = ANY(%s::uuid[])
                """,
                (clip_ids,),
            )
            rows = [dict(row) for row in cur.fetchall()]

    found = {str(row["clip_id"]) for row in rows}
    missing = [clip_id for clip_id in clip_ids if clip_id not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Clip not found: {missing[0]}")

    inputs: list[dict] = []
    for row in rows:
        if row.get("channel_id") != channel_id or row.get("job_user_id") != user_id:
            raise HTTPException(status_code=404, detail="Clip not found")
        if not row.get("input_video_url"):
            raise HTTPException(status_code=400, detail=f"Clip has no render URL: {row['clip_id']}")
        inputs.append(row)
    return inputs


def _input_rows_from_body(body: ProvisionJobCreate, channel_id: str, user_id: str) -> list[dict]:
    rows = _fetch_clip_inputs(body.clip_ids, channel_id, user_id)
    for item in body.items:
        if item.clip_id:
            rows.extend(_fetch_clip_inputs([item.clip_id], channel_id, user_id))
            continue
        if not item.input_video_url:
            raise HTTPException(status_code=400, detail="input_video_url or clip_id is required")
        rows.append(
            {
                "clip_id": None,
                "input_video_url": item.input_video_url,
                "input_title": item.input_title,
                "input_description": item.input_description,
                "main_person": item.main_person,
            }
        )
    return rows


def _update_job_counts(cur, job_id: str) -> None:
    cur.execute(
        """
        UPDATE provision_jobs j
        SET
            item_count = counts.item_count,
            completed_item_count = counts.completed_item_count,
            selected_variant_count = counts.selected_variant_count,
            updated_at = now()
        FROM (
            SELECT
                %s::uuid AS job_id,
                COUNT(DISTINCT i.id)::int AS item_count,
                COUNT(DISTINCT i.id) FILTER (WHERE i.status IN ('planned', 'completed'))::int AS completed_item_count,
                COUNT(DISTINCT v.id) FILTER (WHERE v.review_status = 'selected')::int AS selected_variant_count
            FROM provision_items i
            LEFT JOIN provision_variants v ON v.provision_item_id = i.id
            WHERE i.provision_job_id = %s
        ) counts
        WHERE j.id = counts.job_id
        """,
        (job_id, job_id),
    )


def _r2_key_from_public_url(url: str) -> str:
    if not url:
        raise HTTPException(status_code=400, detail="Variant has no output URL")
    public_base = (settings.R2_PUBLIC_URL or "").rstrip("/")
    if public_base and url.startswith(f"{public_base}/"):
        return unquote(url[len(public_base) + 1 :])
    parsed = urlparse(url)
    key = unquote(parsed.path.lstrip("/"))
    if not key:
        raise HTTPException(status_code=400, detail="Could not determine R2 object key")
    return key


def _variant_download_filename(row: dict) -> str:
    title = (row.get("input_title") or f"provision-{row['id']}").strip()
    mode = (row.get("variant_mode") or "variant").strip()
    return f"{title} - {mode}.mp4"


def _insert_items(cur, job: dict, inputs: list[dict]) -> int:
    if not inputs:
        return 0

    rows = []
    for item in inputs:
        rows.append(
            (
                job["id"],
                job["channel_id"],
                job["user_id"],
                item.get("clip_id"),
                item["input_video_url"],
                item.get("input_title"),
                item.get("input_description"),
                item.get("main_person"),
            )
        )

    inserted_items = execute_values(
        cur,
        """
        INSERT INTO provision_items (
            provision_job_id, channel_id, user_id, clip_id, input_video_url,
            input_title, input_description, main_person
        ) VALUES %s
        RETURNING id
        """,
        rows,
        fetch=True,
    )
    item_ids = [row["id"] if isinstance(row, dict) else row[0] for row in inserted_items]
    if not item_ids:
        cur.execute(
            """
            SELECT id
            FROM provision_items
            WHERE provision_job_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (job["id"], len(rows)),
        )
        item_ids = [row["id"] for row in cur.fetchall()]

    variant_rows = []
    for item_id in item_ids:
        for mode in job.get("variant_modes") or DEFAULT_VARIANT_MODES:
            variant_rows.append(
                (
                    item_id,
                    job["id"],
                    job["channel_id"],
                    job["user_id"],
                    mode,
                )
            )
    if variant_rows:
        execute_values(
            cur,
            """
            INSERT INTO provision_variants (
                provision_item_id, provision_job_id, channel_id, user_id, variant_mode
            ) VALUES %s
            """,
            variant_rows,
        )
    _update_job_counts(cur, str(job["id"]))
    return len(rows)


@router.post("/jobs")
async def create_provision_job(body: ProvisionJobCreate, current_user: dict = Depends(get_current_user)):
    channel_id = _normalize_channel_id(body.channel_id)
    _ensure_channel_owner(channel_id, current_user["id"])
    variant_modes = _normalize_variant_modes(body.variant_modes)
    inputs = _input_rows_from_body(body, channel_id, current_user["id"])
    name = (body.name or "").strip() or f"Provision {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO provision_jobs (
                    channel_id, user_id, name, job_type, status, variant_modes, settings
                )
                VALUES (%s, %s, %s, 'manual', 'draft', %s, %s::jsonb)
                RETURNING *
                """,
                (channel_id, current_user["id"], name, variant_modes, Json(body.settings)),
            )
            job = dict(cur.fetchone())
            inserted = _insert_items(cur, job, inputs)
            cur.execute("SELECT * FROM provision_jobs WHERE id = %s", (job["id"],))
            job = dict(cur.fetchone())

    return {**job, "inserted_items": inserted}


@router.get("/jobs")
async def list_provision_jobs(
    channel_id: str,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    channel_id = _normalize_channel_id(channel_id)
    _ensure_channel_owner(channel_id, current_user["id"])
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM provision_jobs
                WHERE channel_id = %s
                  AND user_id = %s
                  AND job_type = 'manual'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (channel_id, current_user["id"], max(1, min(limit, 200))),
            )
            return [dict(row) for row in cur.fetchall()]


@router.get("/jobs/{job_id}")
async def get_provision_job(job_id: str, current_user: dict = Depends(get_current_user)):
    job = _verify_job_owner(job_id, current_user["id"])
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM provision_items
                WHERE provision_job_id = %s
                ORDER BY created_at ASC
                """,
                (job_id,),
            )
            items = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT *
                FROM provision_variants
                WHERE provision_job_id = %s
                ORDER BY created_at ASC
                """,
                (job_id,),
            )
            variants = [dict(row) for row in cur.fetchall()]
    return {**job, "items": items, "variants": variants}


@router.patch("/jobs/{job_id}")
async def update_provision_job(
    job_id: str,
    body: ProvisionJobUpdate,
    current_user: dict = Depends(get_current_user),
):
    _verify_job_owner(job_id, current_user["id"])
    allowed_statuses = {"draft", "queued", "processing", "completed", "failed", "cancelled"}
    updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}

    if body.name is not None:
        value = body.name.strip()
        if not value:
            raise HTTPException(status_code=400, detail="name must not be empty")
        updates["name"] = value
    if body.status is not None:
        value = body.status.strip().lower()
        if value not in allowed_statuses:
            raise HTTPException(status_code=400, detail="Invalid status")
        updates["status"] = value
        if value in {"completed", "failed", "cancelled"}:
            updates["completed_at"] = datetime.now(timezone.utc)
        if value == "processing":
            updates["started_at"] = datetime.now(timezone.utc)
    if body.variant_modes is not None:
        updates["variant_modes"] = _normalize_variant_modes(body.variant_modes)
    if body.settings is not None:
        updates["settings"] = Json(body.settings)

    assignments = []
    values = []
    for key, value in updates.items():
        assignments.append(f"{key} = %s")
        values.append(value)
    values.extend([job_id, current_user["id"]])

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE provision_jobs
                SET {', '.join(assignments)}
                WHERE id = %s
                  AND user_id = %s
                RETURNING *
                """,
                values,
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Provision job not found")
    return dict(row)


@router.post("/jobs/{job_id}/start")
async def start_provision_job(
    job_id: str,
    body: ProvisionJobStart,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    job = _verify_job_owner(job_id, current_user["id"])
    if job.get("status") == "processing":
        raise HTTPException(status_code=409, detail="Provision job is already processing")

    background_tasks.add_task(run_provision_job, job_id, current_user["id"], body.limit)
    return {
        "ok": True,
        "status": "started",
        "job_id": job_id,
        "limit": body.limit,
    }


@router.post("/jobs/{job_id}/items")
async def add_provision_items(
    job_id: str,
    items: list[ProvisionItemInput],
    current_user: dict = Depends(get_current_user),
):
    job = _verify_job_owner(job_id, current_user["id"])
    if not items:
        raise HTTPException(status_code=400, detail="items must not be empty")
    body = ProvisionJobCreate(channel_id=job["channel_id"], items=items)
    inputs = _input_rows_from_body(body, job["channel_id"], current_user["id"])
    with _db_connect() as conn:
        with conn.cursor() as cur:
            inserted = _insert_items(cur, job, inputs)
    return {"ok": True, "inserted": inserted}


@router.patch("/variants/{variant_id}/review")
async def review_provision_variant(
    variant_id: str,
    body: ProvisionVariantReview,
    current_user: dict = Depends(get_current_user),
):
    review_status = body.review_status.strip().lower()
    if review_status not in ALLOWED_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid review status")

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE provision_variants
                SET review_status = %s,
                    feedback_note = %s,
                    reviewed_at = now(),
                    updated_at = now()
                WHERE id = %s
                  AND user_id = %s
                RETURNING *
                """,
                (review_status, body.feedback_note, variant_id, current_user["id"]),
            )
            variant = cur.fetchone()
            if not variant:
                raise HTTPException(status_code=404, detail="Variant not found")

            if review_status == "selected":
                cur.execute(
                    """
                    UPDATE provision_items
                    SET selected_variant_id = %s,
                        updated_at = now()
                    WHERE id = %s
                      AND user_id = %s
                    """,
                    (variant_id, variant["provision_item_id"], current_user["id"]),
                )
            _update_job_counts(cur, str(variant["provision_job_id"]))

    return dict(variant)


@router.get("/variants/{variant_id}/download")
async def get_provision_variant_download(
    variant_id: str,
    current_user: dict = Depends(get_current_user),
):
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    v.id,
                    v.output_video_url,
                    v.variant_mode,
                    v.status,
                    i.input_title
                FROM provision_variants v
                JOIN provision_items i ON i.id = v.provision_item_id
                WHERE v.id = %s
                  AND v.user_id = %s
                LIMIT 1
                """,
                (variant_id, current_user["id"]),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Provision variant not found")
    if row.get("status") != "completed" or not row.get("output_video_url"):
        raise HTTPException(status_code=400, detail="Provision variant is not ready")

    filename = _variant_download_filename(dict(row))
    r2_key = _r2_key_from_public_url(row["output_video_url"])
    download_url = generate_presigned_download(r2_key, filename, expires_in=900)
    return {"download_url": download_url, "filename": filename}
