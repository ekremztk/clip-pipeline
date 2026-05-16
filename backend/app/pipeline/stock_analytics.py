from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.services.supabase_client import get_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_queue_item(job_id: str) -> Optional[dict]:
    try:
        supabase = get_client()
        if not supabase:
            return None
        result = (
            supabase.table("stock_pipeline_queue")
            .select("*")
            .eq("job_id", job_id)
            .limit(1)
            .execute()
        )
        return (result.data or [None])[0]
    except Exception as e:
        print(f"[StockAnalytics] Queue lookup failed for job {job_id}: {e}")
        return None


def _ensure_source_run(job_id: str, source_duration_s: Optional[float] = None) -> Optional[dict]:
    item = _get_queue_item(job_id)
    if not item:
        return None

    try:
        supabase = get_client()
        if not supabase:
            return None

        payload = {
            "queue_item_id": item["id"],
            "job_id": job_id,
            "channel_id": item["channel_id"],
            "user_id": item["user_id"],
            "batch_id": item["batch_id"],
            "series": item.get("series"),
            "source_url": item["source_url"],
            "r2_key": item.get("r2_key"),
            "source_title": item["video_title"],
            "main_person": item["main_person"],
            "status": "processing",
            "updated_at": _now(),
        }
        if source_duration_s is not None:
            payload["source_duration_s"] = source_duration_s

        result = (
            supabase.table("stock_source_runs")
            .upsert(payload, on_conflict="queue_item_id")
            .execute()
        )
        return (result.data or [None])[0]
    except Exception as e:
        print(f"[StockAnalytics] Source run upsert failed for job {job_id}: {e}")
        return None


def record_s05_candidates(job_id: str, candidates: list[dict], source_duration_s: Optional[float] = None) -> None:
    try:
        source_run = _ensure_source_run(job_id, source_duration_s)
        if not source_run:
            return
        supabase = get_client()
        if not supabase:
            return

        source_run_id = source_run["id"]
        rows = []
        for candidate in candidates or []:
            cid = _as_int(candidate.get("candidate_id"))
            if cid is None:
                continue
            rows.append({
                "source_run_id": source_run_id,
                "queue_item_id": source_run.get("queue_item_id"),
                "job_id": job_id,
                "channel_id": source_run["channel_id"],
                "user_id": source_run["user_id"],
                "batch_id": source_run["batch_id"],
                "main_person": source_run["main_person"],
                "candidate_id": cid,
                "s05_start": _as_float(candidate.get("recommended_start")),
                "s05_end": _as_float(candidate.get("recommended_end")),
                "s05_estimated_duration": _as_float(candidate.get("estimated_duration")),
                "s05_hook_text": candidate.get("hook_text"),
                "s05_end_text": candidate.get("end_text"),
                "s05_reason": candidate.get("reason"),
                "s05_loop_potential": candidate.get("loop_potential"),
                "s05_primary_signal": candidate.get("primary_signal"),
                "s05_content_type": candidate.get("content_type"),
                "s05_needs_context": candidate.get("needs_context"),
                "s05_target_guest_dominance": _as_float(candidate.get("target_guest_dominance")),
                "updated_at": _now(),
            })

        if rows:
            supabase.table("stock_clip_candidates").upsert(rows, on_conflict="job_id,candidate_id").execute()

        supabase.table("stock_source_runs").update({
            "s05_raw_candidates_count": len(candidates or []),
            "s05_valid_candidates_count": len(candidates or []),
            "updated_at": _now(),
        }).eq("job_id", job_id).execute()
    except Exception as e:
        print(f"[StockAnalytics] S05 record failed for job {job_id}: {e}")


def record_s06_evaluation(
    job_id: str,
    sent_candidates: list[dict],
    evaluated_candidates: list[dict],
    passed_candidates: list[dict],
) -> None:
    try:
        source_run = _ensure_source_run(job_id)
        if not source_run:
            return
        supabase = get_client()
        if not supabase:
            return

        passed_ids = {
            str(item.get("candidate_id"))
            for item in passed_candidates or []
            if item.get("candidate_id") is not None
        }
        rows_by_candidate_id: dict[int, dict] = {}
        scores = []
        omitted_count = 0
        for candidate in evaluated_candidates or []:
            cid = _as_int(candidate.get("candidate_id"))
            if cid is None:
                continue
            verdict = str(candidate.get("quality_verdict") or "")
            score = _as_int(candidate.get("score"))
            if score is not None:
                scores.append(score)
            if verdict == "omit":
                omitted_count += 1
            rows_by_candidate_id[cid] = {
                "source_run_id": source_run["id"],
                "queue_item_id": source_run.get("queue_item_id"),
                "job_id": job_id,
                "channel_id": source_run["channel_id"],
                "user_id": source_run["user_id"],
                "batch_id": source_run["batch_id"],
                "main_person": source_run["main_person"],
                "candidate_id": cid,
                "s06_start": _as_float(candidate.get("recommended_start")),
                "s06_end": _as_float(candidate.get("recommended_end")),
                "s06_hook_text": candidate.get("hook_text"),
                "s06_score": score,
                "s06_quality_verdict": verdict or None,
                "s06_quality_notes": candidate.get("quality_notes"),
                "s06_omit_reason": candidate.get("omit_reason") or (candidate.get("quality_notes") if verdict == "omit" else None),
                "s06_content_type": candidate.get("content_type"),
                "s06_clip_strategy_role": candidate.get("clip_strategy_role"),
                "s06_posting_order": _as_int(candidate.get("posting_order")),
                "s06_suggested_title": candidate.get("suggested_title"),
                "s06_suggested_description": candidate.get("suggested_description"),
                "s06_hallucination_flag": candidate.get("s05_hallucination_flag"),
                "passed_to_s07": str(cid) in passed_ids,
                "updated_at": _now(),
            }

        rows = list(rows_by_candidate_id.values())

        if rows:
            supabase.table("stock_clip_candidates").upsert(rows, on_conflict="job_id,candidate_id").execute()

        supabase.table("stock_source_runs").update({
            "s06_sent_candidates_count": len(sent_candidates or []),
            "s06_returned_candidates_count": len(evaluated_candidates or []),
            "s06_omitted_count": omitted_count,
            "s06_passed_count": len(passed_candidates or []),
            "max_score": max(scores) if scores else None,
            "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
            "updated_at": _now(),
        }).eq("job_id", job_id).execute()
    except Exception as e:
        print(f"[StockAnalytics] S06 record failed for job {job_id}: {e}")


def record_s07_cuts(job_id: str, cut_results: list[dict]) -> None:
    try:
        source_run = _ensure_source_run(job_id)
        if not source_run:
            return
        supabase = get_client()
        if not supabase:
            return

        for clip in cut_results or []:
            cid = _as_int(clip.get("candidate_id"))
            if cid is None:
                continue
            supabase.table("stock_clip_candidates").update({
                "passed_to_s07": True,
                "s07_final_start": _as_float(clip.get("final_start")),
                "s07_final_end": _as_float(clip.get("final_end")),
                "s07_final_duration_s": _as_float(clip.get("final_duration_s")),
                "updated_at": _now(),
            }).eq("job_id", job_id).eq("candidate_id", cid).execute()

        supabase.table("stock_source_runs").update({
            "s07_cut_count": len(cut_results or []),
            "updated_at": _now(),
        }).eq("job_id", job_id).execute()
    except Exception as e:
        print(f"[StockAnalytics] S07 record failed for job {job_id}: {e}")


def get_clip_stock_fields(job_id: str, candidate_id: Any) -> dict:
    try:
        cid = _as_int(candidate_id)
        source_run = _ensure_source_run(job_id)
        if not source_run or cid is None:
            return {}
        supabase = get_client()
        if not supabase:
            return {}
        candidate = (
            supabase.table("stock_clip_candidates")
            .select("id")
            .eq("job_id", job_id)
            .eq("candidate_id", cid)
            .limit(1)
            .execute()
        )
        candidate_id_db = (candidate.data or [{}])[0].get("id")
        return {
            "stock_batch_id": source_run["batch_id"],
            "stock_queue_item_id": source_run.get("queue_item_id"),
            "stock_source_run_id": source_run["id"],
            "stock_candidate_id": candidate_id_db,
            "main_person": source_run["main_person"],
        }
    except Exception as e:
        print(f"[StockAnalytics] Clip stock fields failed for job {job_id}: {e}")
        return {}


def record_final_clip(job_id: str, candidate_id: Any, clip_id: Optional[str]) -> None:
    if not clip_id:
        return
    try:
        cid = _as_int(candidate_id)
        if cid is None:
            return
        supabase = get_client()
        if not supabase:
            return
        supabase.table("stock_clip_candidates").update({
            "final_clip_id": clip_id,
            "updated_at": _now(),
        }).eq("job_id", job_id).eq("candidate_id", cid).execute()
    except Exception as e:
        print(f"[StockAnalytics] Final clip link failed for job {job_id}: {e}")


def record_source_completed(job_id: str, final_clip_count: int) -> None:
    try:
        source_run = _ensure_source_run(job_id)
        if not source_run:
            return
        supabase = get_client()
        if not supabase:
            return
        supabase.table("stock_source_runs").update({
            "status": "completed",
            "final_clip_count": final_clip_count,
            "completed_at": _now(),
            "updated_at": _now(),
        }).eq("job_id", job_id).execute()
    except Exception as e:
        print(f"[StockAnalytics] Source completion failed for job {job_id}: {e}")


def record_source_failed(job_id: str, failed_step: str, error_message: str) -> None:
    try:
        source_run = _ensure_source_run(job_id)
        if not source_run:
            return
        supabase = get_client()
        if not supabase:
            return
        supabase.table("stock_source_runs").update({
            "status": "failed",
            "failed_step": failed_step,
            "error_message": error_message[:2000],
            "completed_at": _now(),
            "updated_at": _now(),
        }).eq("job_id", job_id).execute()
    except Exception as e:
        print(f"[StockAnalytics] Source failure record failed for job {job_id}: {e}")
