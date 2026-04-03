"""
Director Pipeline Executor — test pipeline runs and monitoring.
Director can create test jobs, monitor progress, and analyze results.
"""

from app.services.supabase_client import get_client
from app.director.events import director_events
from app.director.tools.database import _run_sql


def create_test_job(
    video_url: str | None = None,
    video_path: str | None = None,
    channel_id: str = "speedy_cast",
    title: str = "Director Test Run",
    guest_name: str | None = None,
) -> dict:
    """Create and start a test pipeline job."""
    try:
        if not video_url and not video_path:
            from app.config import settings
            test_video = getattr(settings, 'DIRECTOR_TEST_VIDEO_URL', None)
            if not test_video:
                return {
                    "error": "Test videosu belirtilmedi. "
                    "video_url parametresi ver veya DIRECTOR_TEST_VIDEO_URL env var'ı ayarla."
                }
            video_url = test_video

        # Check daily limit
        from app.director.config import MAX_DAILY_TEST_PIPELINES
        today_count = _run_sql("""
            SELECT COUNT(*) AS cnt FROM jobs
            WHERE is_test_run = true
              AND created_at > now() - interval '24 hours'
        """)
        if today_count and int((today_count[0] or {}).get("cnt") or 0) >= MAX_DAILY_TEST_PIPELINES:
            return {"error": f"Günlük test limiti ({MAX_DAILY_TEST_PIPELINES}) doldu."}

        client = get_client()
        job_data = {
            "channel_id": channel_id,
            "video_title": f"[TEST] {title}",
            "guest_name": guest_name,
            "status": "queued",
            "is_test_run": True,
        }
        if video_path:
            job_data["video_path"] = video_path

        res = client.table("jobs").insert(job_data).execute()
        if not res.data:
            return {"error": "Job oluşturulamadı"}

        job_id = res.data[0]["id"]

        # Start pipeline in background
        import asyncio
        try:
            asyncio.create_task(
                _run_pipeline_async(job_id, video_url or video_path,
                                    title, guest_name, channel_id)
            )
        except RuntimeError:
            import threading
            thread = threading.Thread(
                target=_run_pipeline_sync,
                args=(job_id, video_url or video_path, title, guest_name, channel_id)
            )
            thread.daemon = True
            thread.start()

        director_events.emit_sync(
            module="director", event="test_pipeline_started",
            payload={"job_id": job_id, "channel_id": channel_id, "is_test_run": True},
            channel_id=channel_id,
        )

        return {
            "ok": True,
            "job_id": job_id,
            "status": "queued",
            "message": (f"Test pipeline başlatıldı. Job ID: {job_id}. "
                        f"Durumu kontrol etmek için: get_test_pipeline_status('{job_id}')")
        }

    except Exception as e:
        return {"error": f"Test pipeline oluşturma hatası: {e}"}


async def _run_pipeline_async(job_id, video_source, title, guest_name, channel_id):
    try:
        from app.pipeline.orchestrator import run_pipeline
        await run_pipeline(job_id, video_source, title, guest_name, channel_id)
    except Exception as e:
        print(f"[Director] Test pipeline failed: {e}")
        director_events.emit_sync(
            module="director", event="test_pipeline_failed",
            payload={"job_id": job_id, "error": str(e)}
        )


def _run_pipeline_sync(job_id, video_source, title, guest_name, channel_id):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            _run_pipeline_async(job_id, video_source, title, guest_name, channel_id)
        )
    finally:
        loop.close()


def get_test_pipeline_status(job_id: str) -> dict:
    """Detailed status of a running or completed test pipeline."""
    try:
        client = get_client()
        job_res = client.table("jobs").select("*").eq("id", job_id).single().execute()
        if not job_res.data:
            return {"error": f"Job {job_id} bulunamadı"}

        job = job_res.data

        steps = _run_sql("""
            SELECT step_name, step_number, status, duration_ms,
                   output_summary, error_message, token_usage, created_at
            FROM pipeline_audit_log
            WHERE job_id = %s
            ORDER BY step_number ASC
        """, (job_id,))

        clips = []
        if job.get("status") in ("completed", "partial"):
            clip_res = (client.table("clips")
                .select("clip_index,content_type,quality_verdict,overall_confidence,"
                        "standalone_score,hook_score,arc_score,hook_text,"
                        "suggested_title,duration_s,file_url")
                .eq("job_id", job_id)
                .order("clip_index")
                .execute())
            clips = clip_res.data or []

        total_cost = sum(
            float((s.get("token_usage") or {}).get("cost_usd", 0) or 0)
            for s in steps
        )
        total_duration = sum(int(s.get("duration_ms") or 0) for s in steps)
        pass_clips = [c for c in clips if c.get("quality_verdict") == "pass"]

        return {
            "job_id": job_id,
            "status": job.get("status"),
            "current_step": job.get("current_step"),
            "progress_pct": job.get("progress_pct", 0),
            "total_duration_min": round(total_duration / 60000, 1),
            "total_cost_usd": round(total_cost, 4),
            "steps": [
                {
                    "name": s.get("step_name"),
                    "status": s.get("status"),
                    "duration_s": round(int(s.get("duration_ms") or 0) / 1000, 1),
                    "error": s.get("error_message"),
                }
                for s in steps
            ],
            "clips_summary": {
                "total": len(clips),
                "pass": len(pass_clips),
                "fail": len(clips) - len(pass_clips),
                "avg_confidence": (
                    round(sum(c.get("overall_confidence", 0) or 0 for c in clips) / len(clips), 2)
                    if clips else None
                ),
            },
            "clips": clips,
            "is_test_run": job.get("is_test_run", False),
        }

    except Exception as e:
        return {"error": f"Status check hatası: {e}"}


def get_active_pipelines() -> dict:
    """List all currently running pipelines."""
    try:
        rows = _run_sql("""
            SELECT id, channel_id, video_title, status, current_step,
                   progress_pct, created_at, is_test_run
            FROM jobs
            WHERE status IN ('queued', 'processing')
            ORDER BY created_at DESC
            LIMIT 10
        """)
        return {"active_count": len(rows), "pipelines": rows}
    except Exception as e:
        return {"error": str(e)}


def analyze_test_results(job_id: str) -> dict:
    """Deep analysis of a completed test pipeline."""
    try:
        status = get_test_pipeline_status(job_id)
        if status.get("error"):
            return status

        if status.get("status") not in ("completed", "partial"):
            return {
                "error": f"Pipeline henüz tamamlanmadı. Durum: {status.get('status')}",
                "current_step": status.get("current_step"),
                "progress": status.get("progress_pct"),
            }

        clips = status.get("clips", [])
        clips_summary = status.get("clips_summary", {})
        pass_rate = 0
        if clips_summary.get("total", 0) > 0:
            pass_rate = clips_summary["pass"] / clips_summary["total"] * 100

        recommendations = []
        step_analysis = []
        for step in status.get("steps", []):
            note = {"name": step["name"], "duration_s": step["duration_s"], "status": step["status"]}
            if "s05" in (step.get("name") or "") and step["duration_s"] > 180:
                note["warning"] = f"S05 normalden yavaş: {step['duration_s']}s (hedef: <180s)"
                recommendations.append("S05 yavaş — video boyutu veya rate limit kontrol edilmeli.")
            if step.get("error"):
                note["error"] = step["error"]
            step_analysis.append(note)

        overall = (
            "İYİ — Pass rate ve süre hedeflerde." if pass_rate >= 50 and status.get("total_duration_min", 99) < 8
            else "ORTA — Pass rate kabul edilebilir ama iyileştirme var." if pass_rate >= 30
            else "ZAYIF — Pass rate düşük, S05/S06 prompt veya DNA incelenmeli."
        )

        try:
            from app.director.tools.memory import save_memory
            save_memory(
                content=(f"Test pipeline ({job_id}): {overall} "
                         f"Pass rate: %{pass_rate:.1f}, {len(clips)} klip, "
                         f"${status.get('total_cost_usd', 0):.4f} maliyet."),
                type="learning", tags=["test_run", "pipeline_analysis"], source="auto",
            )
        except Exception:
            pass

        return {
            "job_id": job_id,
            "overall_assessment": overall,
            "step_analysis": step_analysis,
            "clip_analysis": {
                "pass_rate": round(pass_rate, 1),
                "total_clips": clips_summary.get("total", 0),
                "pass_clips": clips_summary.get("pass", 0),
                "avg_confidence": clips_summary.get("avg_confidence"),
                "content_types": list(set(c.get("content_type", "unknown") for c in clips)),
            },
            "cost_analysis": {
                "total_cost_usd": status.get("total_cost_usd", 0),
                "cost_per_clip": round(status.get("total_cost_usd", 0) / max(len(clips), 1), 4),
                "total_duration_min": status.get("total_duration_min", 0),
            },
            "recommendations": recommendations,
        }

    except Exception as e:
        return {"error": f"Analiz hatası: {e}"}
