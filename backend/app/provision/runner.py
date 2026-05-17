from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from app.provision.steps import p01_fetch_input, p02_audio_analysis, p03_edit_plan, p04_render_variant
from app.services.supabase_client import get_db_url


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _db_connect():
    db_url = get_db_url()
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)


def _update_job(cur, job_id: str, **fields: Any) -> None:
    fields["updated_at"] = _now()
    assignments = [f"{key} = %s" for key in fields]
    values = list(fields.values()) + [job_id]
    cur.execute(
        f"UPDATE provision_jobs SET {', '.join(assignments)} WHERE id = %s",
        values,
    )


def _update_item(cur, item_id: str, **fields: Any) -> None:
    fields["updated_at"] = _now()
    assignments = [f"{key} = %s" for key in fields]
    values = list(fields.values()) + [item_id]
    cur.execute(
        f"UPDATE provision_items SET {', '.join(assignments)} WHERE id = %s",
        values,
    )


def _update_variant(cur, variant_id: str, **fields: Any) -> None:
    fields["updated_at"] = _now()
    assignments = [f"{key} = %s" for key in fields]
    values = list(fields.values()) + [variant_id]
    cur.execute(
        f"UPDATE provision_variants SET {', '.join(assignments)} WHERE id = %s",
        values,
    )


def _refresh_job_counts(cur, job_id: str) -> None:
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


def _load_job(job_id: str, user_id: str) -> dict[str, Any]:
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
        raise RuntimeError("Provision job not found")
    return dict(row)


def _load_items(job_id: str, limit: int) -> list[dict[str, Any]]:
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM provision_items
                WHERE provision_job_id = %s
                  AND status IN ('queued', 'failed')
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (job_id, max(1, limit)),
            )
            return [dict(row) for row in cur.fetchall()]


def _load_variants(item_id: str) -> list[dict[str, Any]]:
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM provision_variants
                WHERE provision_item_id = %s
                  AND status IN ('queued', 'failed')
                ORDER BY created_at ASC
                """,
                (item_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def _mark_job_failed(job_id: str, error: str) -> None:
    with _db_connect() as conn:
        with conn.cursor() as cur:
            _update_job(
                cur,
                job_id,
                status="failed",
                current_step="failed",
                error_message=error[:2000],
                completed_at=_now(),
            )


def _process_item(job: dict[str, Any], item: dict[str, Any]) -> None:
    item_id = str(item["id"])
    job_id = str(job["id"])
    input_path = ""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                _update_item(
                    cur,
                    item_id,
                    status="analyzing",
                    current_step="p01_fetch_input",
                    current_step_number=1,
                    progress_pct=10,
                    error_message=None,
                    started_at=_now(),
                )
                _update_job(cur, job_id, current_step="p01_fetch_input", current_step_number=1, progress_pct=15)

        input_path = p01_fetch_input.run(item, item_id)

        with _db_connect() as conn:
            with conn.cursor() as cur:
                _update_item(
                    cur,
                    item_id,
                    current_step="p02_audio_analysis",
                    current_step_number=2,
                    progress_pct=35,
                )
                _update_job(cur, job_id, current_step="p02_audio_analysis", current_step_number=2, progress_pct=35)

        analysis = p02_audio_analysis.run(input_path, item_id)
        words = analysis["words"]
        transcript_text = analysis["transcript_text"]
        audio_analysis = analysis["audio_analysis"]

        with _db_connect() as conn:
            with conn.cursor() as cur:
                _update_item(
                    cur,
                    item_id,
                    nova_transcript=Json(analysis["nova_transcript"]),
                    audio_analysis=Json(audio_analysis),
                    current_step="p03_edit_plan",
                    current_step_number=3,
                    progress_pct=60,
                )
                _update_job(cur, job_id, current_step="p03_edit_plan", current_step_number=3, progress_pct=60)

        variants = _load_variants(item_id)
        planned_count = 0
        for index, variant in enumerate(variants, start=1):
            variant_id = str(variant["id"])
            variant_mode = str(variant["variant_mode"])
            try:
                with _db_connect() as conn:
                    with conn.cursor() as cur:
                        _update_variant(
                            cur,
                            variant_id,
                            status="planning",
                            current_step="p03_edit_plan",
                            current_step_number=3,
                            progress_pct=35,
                            error_message=None,
                            started_at=_now(),
                        )

                plan = p03_edit_plan.run(
                    video_path=input_path,
                    item=item,
                    variant_mode=variant_mode,
                    transcript_text=transcript_text,
                    words=words,
                    audio_analysis=audio_analysis,
                )

                with _db_connect() as conn:
                    with conn.cursor() as cur:
                        _update_variant(
                            cur,
                            variant_id,
                            status="planned",
                            current_step="planned",
                            current_step_number=3,
                            progress_pct=70,
                            edit_plan=Json(plan),
                            score=plan.get("score"),
                        )

                with _db_connect() as conn:
                    with conn.cursor() as cur:
                        _update_variant(
                            cur,
                            variant_id,
                            status="rendering",
                            current_step="p04_render_variant",
                            current_step_number=4,
                            progress_pct=82,
                        )
                        _update_job(cur, job_id, current_step="p04_render_variant", current_step_number=4, progress_pct=82)

                render_result = p04_render_variant.run(input_path, plan, variant_id)

                with _db_connect() as conn:
                    with conn.cursor() as cur:
                        _update_variant(
                            cur,
                            variant_id,
                            status="completed",
                            current_step="completed",
                            current_step_number=4,
                            progress_pct=100,
                            validation_report=Json({"render": render_result}),
                            output_video_url=render_result["output_video_url"],
                            duration_s=render_result["duration_s"],
                            completed_at=_now(),
                        )
                planned_count += 1
                print(f"[Provision] Rendered variant {index}/{len(variants)} item={item_id} mode={variant_mode}")
            except Exception as exc:
                print(f"[Provision] Variant {variant_id} failed: {exc}")
                with _db_connect() as conn:
                    with conn.cursor() as cur:
                        _update_variant(
                            cur,
                            variant_id,
                            status="failed",
                            current_step="failed",
                            error_message=str(exc)[:2000],
                            completed_at=_now(),
                        )

        with _db_connect() as conn:
            with conn.cursor() as cur:
                if planned_count:
                    _update_item(
                        cur,
                        item_id,
                        status="completed",
                        current_step="completed",
                        current_step_number=4,
                        progress_pct=100,
                        completed_at=_now(),
                    )
                else:
                    _update_item(
                        cur,
                        item_id,
                        status="failed",
                        current_step="failed",
                        error_message="No variants were planned",
                        completed_at=_now(),
                    )
                _refresh_job_counts(cur, job_id)
    except Exception as exc:
        print(f"[Provision] Item {item_id} failed: {exc}")
        with _db_connect() as conn:
            with conn.cursor() as cur:
                _update_item(
                    cur,
                    item_id,
                    status="failed",
                    current_step="failed",
                    error_message=str(exc)[:2000],
                    completed_at=_now(),
                )
                _refresh_job_counts(cur, job_id)
    finally:
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except Exception:
                pass


def run_provision_job(job_id: str, user_id: str, limit: int = 1) -> None:
    """Run the plan-generation phase for queued items in one Provision job."""
    job = _load_job(job_id, user_id)
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                _update_job(
                    cur,
                    job_id,
                    status="processing",
                    current_step="starting",
                    current_step_number=0,
                    progress_pct=5,
                    error_message=None,
                    started_at=_now(),
                )

        items = _load_items(job_id, limit)
        if not items:
            with _db_connect() as conn:
                with conn.cursor() as cur:
                    _refresh_job_counts(cur, job_id)
                    _update_job(
                        cur,
                        job_id,
                        status="completed",
                        current_step="completed",
                        current_step_number=3,
                        progress_pct=100,
                        completed_at=_now(),
                    )
            return

        for item in items:
            _process_item(job, item)

        with _db_connect() as conn:
            with conn.cursor() as cur:
                _refresh_job_counts(cur, job_id)
                cur.execute(
                    """
                    SELECT COUNT(*) AS queued_count
                    FROM provision_items
                    WHERE provision_job_id = %s
                      AND status IN ('queued', 'failed')
                    """,
                    (job_id,),
                )
                queued_count = int((cur.fetchone() or {}).get("queued_count") or 0)
                _update_job(
                    cur,
                    job_id,
                    status="queued" if queued_count else "completed",
                    current_step="waiting" if queued_count else "completed",
                    current_step_number=3,
                    progress_pct=80 if queued_count else 100,
                    completed_at=None if queued_count else _now(),
                )
    except Exception as exc:
        print(f"[Provision] Job {job_id} failed: {exc}")
        _mark_job_failed(job_id, str(exc))


async def run_provision_job_async(job_id: str, user_id: str, limit: int = 1) -> None:
    import asyncio

    await asyncio.to_thread(run_provision_job, job_id, user_id, limit)
