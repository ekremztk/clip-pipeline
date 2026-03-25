"""
Director A/B Test Runner — run the same video with two pipeline configs and compare results.
Depends on pipeline_executor for creating test jobs.
"""

from app.director.tools.pipeline_executor import create_test_job, get_test_pipeline_status
from app.director.tools.memory import save_memory
from app.director.events import director_events
from app.director.config import MAX_DAILY_AB_TESTS
from app.services.supabase_client import get_client
from app.director.tools.database import _run_sql


def _check_daily_ab_limit() -> bool:
    """Return True if daily A/B test limit not exceeded."""
    try:
        rows = _run_sql("""
            SELECT COUNT(*) AS cnt FROM director_test_runs
            WHERE created_at > now() - interval '24 hours'
              AND (params->>'type') = 'ab_test'
        """)
        count = int(rows[0].get("cnt", 0)) if rows else 0
        return count < MAX_DAILY_AB_TESTS
    except Exception:
        return True


def start_ab_test(
    test_name: str,
    channel_id: str = "speedy_cast",
    video_url: str | None = None,
    description: str = "",
) -> dict:
    """
    Start an A/B test — runs two parallel pipelines with the same video.
    Returns test_id and both job IDs for tracking.
    """
    try:
        if not _check_daily_ab_limit():
            return {"error": f"Günlük A/B test limiti ({MAX_DAILY_AB_TESTS}) aşıldı. Yarın tekrar dene."}

        client = get_client()

        res = client.table("director_test_runs").insert({
            "test_name": test_name,
            "channel_id": channel_id,
            "description": description,
            "status": "running",
            "params": {"video_url": video_url, "type": "ab_test"},
        }).execute()
        test_id = res.data[0]["id"] if res.data else None

        run_a = create_test_job(
            video_url=video_url, channel_id=channel_id,
            title=f"[A/B Test A] {test_name}",
        )
        if run_a.get("error"):
            return {"error": f"Run A failed: {run_a['error']}"}

        run_b = create_test_job(
            video_url=video_url, channel_id=channel_id,
            title=f"[A/B Test B] {test_name}",
        )
        if run_b.get("error"):
            return {"error": f"Run B failed: {run_b['error']}"}

        if test_id:
            client.table("director_test_runs").update({
                "params": {
                    "video_url": video_url, "type": "ab_test",
                    "run_a_job_id": run_a["job_id"],
                    "run_b_job_id": run_b["job_id"],
                },
            }).eq("id", test_id).execute()

        director_events.emit_sync(
            module="director", event="ab_test_started",
            payload={
                "test_id": test_id, "test_name": test_name,
                "run_a_job_id": run_a["job_id"],
                "run_b_job_id": run_b["job_id"],
            },
        )

        return {
            "ok": True,
            "test_id": test_id,
            "test_name": test_name,
            "run_a_job_id": run_a["job_id"],
            "run_b_job_id": run_b["job_id"],
            "message": (
                f"A/B test started. Two pipelines running in parallel.\n"
                f"When complete: compare_ab_test('{test_id}')"
            ),
        }

    except Exception as e:
        return {"error": str(e)}


def compare_ab_test(test_id: str) -> dict:
    """Compare results of a completed A/B test's two runs."""
    try:
        client = get_client()
        test_res = client.table("director_test_runs").select("*").eq("id", test_id).single().execute()
        if not test_res.data:
            return {"error": f"Test {test_id} not found"}

        params = test_res.data.get("params") or {}
        run_a_id = params.get("run_a_job_id")
        run_b_id = params.get("run_b_job_id")
        if not run_a_id or not run_b_id:
            return {"error": "Test has no run job IDs"}

        status_a = get_test_pipeline_status(run_a_id)
        status_b = get_test_pipeline_status(run_b_id)

        if status_a.get("status") != "completed" or status_b.get("status") != "completed":
            return {
                "error": "Both runs must be completed before comparing",
                "run_a_status": status_a.get("status"),
                "run_b_status": status_b.get("status"),
            }

        def _metrics(status):
            c = status.get("clips_summary", {})
            total = c.get("total", 0)
            passed = c.get("pass", 0)
            return {
                "total_clips": total,
                "pass_clips": passed,
                "pass_rate": round(passed / max(total, 1) * 100, 1),
                "avg_confidence": c.get("avg_confidence"),
                "total_cost_usd": status.get("total_cost_usd", 0),
                "total_duration_min": status.get("total_duration_min", 0),
            }

        ma = _metrics(status_a)
        mb = _metrics(status_b)

        if ma["pass_rate"] > mb["pass_rate"] + 5:
            winner, reason = "A", f"Run A %{ma['pass_rate']} vs Run B %{mb['pass_rate']} pass rate"
        elif mb["pass_rate"] > ma["pass_rate"] + 5:
            winner, reason = "B", f"Run B %{mb['pass_rate']} vs Run A %{ma['pass_rate']} pass rate"
        elif ma["total_cost_usd"] < mb["total_cost_usd"] * 0.8:
            winner, reason = "A", "Similar pass rate but Run A is cheaper"
        elif mb["total_cost_usd"] < ma["total_cost_usd"] * 0.8:
            winner, reason = "B", "Similar pass rate but Run B is cheaper"
        else:
            winner, reason = "tie", "No significant difference"

        comparison = {
            "test_id": test_id,
            "test_name": test_res.data.get("test_name"),
            "run_a": {"job_id": run_a_id, **ma},
            "run_b": {"job_id": run_b_id, **mb},
            "winner": winner,
            "reason": reason,
            "deltas": {
                "pass_rate_diff": round(ma["pass_rate"] - mb["pass_rate"], 1),
                "cost_diff_usd": round(ma["total_cost_usd"] - mb["total_cost_usd"], 4),
            },
        }

        client.table("director_test_runs").update(
            {"status": "completed", "result": comparison}
        ).eq("id", test_id).execute()

        save_memory(
            content=(
                f"A/B Test '{test_res.data.get('test_name')}': Winner={winner}. {reason}. "
                f"A: %{ma['pass_rate']} pass, ${ma['total_cost_usd']:.4f}. "
                f"B: %{mb['pass_rate']} pass, ${mb['total_cost_usd']:.4f}."
            ),
            type="learning", tags=["ab_test"], source="auto",
        )

        return comparison

    except Exception as e:
        return {"error": str(e)}
