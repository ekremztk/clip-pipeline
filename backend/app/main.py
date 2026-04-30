from dotenv import load_dotenv

# Load .env variables at the top
load_dotenv()

import logging
import sentry_sdk

class _SuppressJobsPolling(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "GET /jobs" not in msg

logging.getLogger("uvicorn.access").addFilter(_SuppressJobsPolling())
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings

# Sentry — must init before FastAPI app creation
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=0.2,
        profiles_sample_rate=0.1,
    )
    print("[Sentry] Initialized")

async def _startup_analysis():
    """On startup: if no analysis in last 24h, run one to seed the dashboard."""
    import asyncio
    await asyncio.sleep(30)  # wait for app to fully start
    try:
        from app.director.tools.database import _run_sql
        rows = _run_sql("""
            SELECT COUNT(*) AS cnt FROM director_analyses
            WHERE timestamp > now() - interval '24 hours'
        """)
        recent = int((rows[0] or {}).get("cnt", 0)) if rows else 0
        if recent == 0:
            print("[Startup] No recent analysis found — running initial analysis...")
            _run_daily_analysis()
        else:
            print(f"[Startup] {recent} recent analyses found — skipping startup analysis.")
    except Exception as e:
        print(f"[Startup] analysis check error: {e}")


async def _health_pulse_scheduler():
    """Refresh health pulse cache every 5 minutes."""
    import asyncio
    from app.director.router import _compute_health_pulse, _health_pulse_cache
    await asyncio.sleep(10)  # let app fully start
    while True:
        try:
            result = await asyncio.get_event_loop().run_in_executor(None, _compute_health_pulse)
            _health_pulse_cache.clear()
            _health_pulse_cache.update(result)
            print(f"[HealthPulse] score={result.get('score')} status={result.get('status')}")
        except Exception as e:
            print(f"[HealthPulse] error: {e}")
        await asyncio.sleep(300)  # 5 min


async def _proactive_scheduler():
    """Run proactive trigger checks every hour."""
    import asyncio
    from app.director.proactive import run_proactive_checks
    await asyncio.sleep(60)  # wait 1 min after startup
    while True:
        try:
            await asyncio.get_event_loop().run_in_executor(None, run_proactive_checks)
        except Exception as e:
            print(f"[Proactive] Scheduler error: {e}")
        await asyncio.sleep(3600)  # 1 hour


async def _r2_ttl_scheduler():
    """
    Daily cleanup of non-pipeline R2 uploads.
    Deletes debug/, gaming-debug/, reframe-uploads/, upload_sources/ objects older than 24h.
    Also expires stale video_uploads rows (>24h, never consumed).
    Pipeline prefixes (source_videos/, reframe/, {job_id}/) are cleaned
    synchronously by the orchestrator when a pipeline finishes — this scheduler
    is the safety net for manual/debug uploads + abandoned direct uploads.
    """
    import asyncio
    from datetime import datetime, timezone, timedelta
    from app.services.r2_client import get_r2_client

    TTL_PREFIXES = ["debug/", "gaming-debug/", "reframe-uploads/", "upload_sources/"]
    TTL_HOURS = 24

    await asyncio.sleep(180)  # wait 3 min after startup
    while True:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=TTL_HOURS)
            s3 = get_r2_client()
            bucket = settings.R2_BUCKET_NAME
            total_deleted = 0
            for prefix in TTL_PREFIXES:
                to_delete: list[dict] = []
                paginator = s3.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                    for obj in page.get("Contents", []) or []:
                        last_mod = obj.get("LastModified")
                        if last_mod and last_mod < cutoff:
                            to_delete.append({"Key": obj["Key"]})
                        if len(to_delete) >= 1000:
                            s3.delete_objects(
                                Bucket=bucket,
                                Delete={"Objects": to_delete, "Quiet": True},
                            )
                            total_deleted += len(to_delete)
                            to_delete = []
                if to_delete:
                    s3.delete_objects(
                        Bucket=bucket,
                        Delete={"Objects": to_delete, "Quiet": True},
                    )
                    total_deleted += len(to_delete)
            if total_deleted:
                print(f"[R2TTL] Deleted {total_deleted} objects older than {TTL_HOURS}h")

            # Clean up video_uploads rows + their R2 objects:
            # 1. consumed=false + expired → abandoned uploads, safe to delete
            # 2. consumed=true + older than 48h → pipeline is long done, delete R2 object too
            try:
                from app.services.supabase_client import get_client
                sb = get_client()
                now = datetime.now(timezone.utc)

                # Abandoned (never consumed, expired)
                sb.table("video_uploads") \
                    .delete() \
                    .eq("consumed", False) \
                    .lt("expires_at", now.isoformat()) \
                    .execute()

                # Consumed but old — delete R2 objects then DB rows
                old_cutoff = (now - timedelta(hours=48)).isoformat()
                old_rows = (
                    sb.table("video_uploads")
                    .select("id,r2_key")
                    .eq("consumed", True)
                    .lt("created_at", old_cutoff)
                    .execute()
                )
                r2_deleted = 0
                for row in old_rows.data or []:
                    r2_key = row.get("r2_key")
                    if r2_key:
                        try:
                            s3.delete_object(Bucket=bucket, Key=r2_key)
                            r2_deleted += 1
                        except Exception:
                            pass
                if old_rows.data:
                    ids = [r["id"] for r in old_rows.data]
                    sb.table("video_uploads").delete().in_("id", ids).execute()
                    print(f"[R2TTL] Cleaned {len(ids)} consumed uploads, {r2_deleted} R2 objects deleted")
            except Exception as e:
                print(f"[R2TTL] video_uploads DB cleanup error: {e}")
        except Exception as e:
            print(f"[R2TTL] error: {e}")
        await asyncio.sleep(86400)  # once a day


async def _analysis_scheduler():
    """Run AI analysis every 6 hours. Weekly digest on Mondays."""
    import asyncio
    from datetime import datetime, timezone
    await asyncio.sleep(120)  # wait 2 min after startup
    while True:
        try:
            now = datetime.now(timezone.utc)
            # Every 6 hours: 00:00, 06:00, 12:00, 18:00 UTC
            if now.hour % 6 == 0 and now.minute < 5:
                await asyncio.get_event_loop().run_in_executor(
                    None, _run_daily_analysis
                )
            # Weekly digest: Monday 09:00 UTC
            if now.weekday() == 0 and now.hour == 9 and now.minute < 5:
                await asyncio.get_event_loop().run_in_executor(
                    None, _run_weekly_digest
                )
        except Exception as e:
            print(f"[AnalysisScheduler] error: {e}")
        await asyncio.sleep(300)  # check every 5 minutes


def _run_daily_analysis():
    """Synchronous: trigger real AI analysis and proactive checks."""
    try:
        from app.director.router import _run_ai_analysis
        result = _run_ai_analysis(module="all", triggered_by="scheduled")
        print(f"[DailyAnalysis] AI analysis done: score={result.get('overall_score')} id={result.get('analysis_id')}")
        from app.director.proactive import run_proactive_checks
        run_proactive_checks()
        print("[DailyAnalysis] Proactive checks done")
    except Exception as e:
        print(f"[DailyAnalysis] error: {e}")


def _run_weekly_digest():
    """Synchronous: generate weekly digest and save to director_analyses."""
    try:
        from app.director.tools.database import get_pipeline_stats, get_clip_analysis, get_pass_rate_trend
        from app.services.supabase_client import get_client
        from datetime import datetime, timezone

        pipeline = get_pipeline_stats(7)
        clips = get_clip_analysis(None, 7)
        trend = get_pass_rate_trend()

        s = pipeline.get("summary", {})
        ca = clips.get("analysis", {})

        summary = {
            "period": "7 days",
            "total_jobs": int(s.get("total_jobs", 0) or 0),
            "total_clips": int(ca.get("total_clips", 0) or 0),
            "pass_count": int(ca.get("pass_count", 0) or 0),
            "avg_confidence": float(ca.get("avg_confidence", 0) or 0),
            "trend": trend,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        client = get_client()
        client.table("director_analyses").insert({
            "module_name": "all",
            "triggered_by": "scheduled",
            "score": 0,
            "subscores": {},
            "findings": [{"key": "weekly_digest", "data": summary}],
            "recommendations": [],
        }).execute()
        print("[WeeklyDigest] Saved to director_analyses")
        try:
            from app.director.notifier import notify_weekly_digest
            notify_weekly_digest(summary)
        except Exception:
            pass
    except Exception as e:
        print(f"[WeeklyDigest] error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    startup_task = asyncio.create_task(_startup_analysis())
    pulse_task = asyncio.create_task(_health_pulse_scheduler())
    proactive_task = asyncio.create_task(_proactive_scheduler())
    daily_task = asyncio.create_task(_analysis_scheduler())
    r2_ttl_task = asyncio.create_task(_r2_ttl_scheduler())
    yield
    # Cleanup Director connection pool
    try:
        from app.director.tools.database import _connection_pool
        if _connection_pool and not _connection_pool.closed:
            _connection_pool.closeall()
            print("[DB] Director connection pool closed.")
    except Exception:
        pass
    for task in [startup_task, pulse_task, proactive_task, daily_task, r2_ttl_task]:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

from app.api.routes import jobs, clips, downloads, channels, feedback, captions, proxy, youtube_metadata, reframe, voice_library
from app.api.websocket import progress
from app.director.router import router as director_router
from app.limiter import limiter

# CORS — explicit whitelist only
_ALLOWED_ORIGINS = [
    "https://clip.prognot.com",
    "https://edit.prognot.com",
    "https://prognot.com",
    "https://www.prognot.com",
]
if settings.ENVIRONMENT == "development":
    _ALLOWED_ORIGINS += ["http://localhost:3000", "http://localhost:3001"]

app = FastAPI(
    title="Prognot Clip Pipeline",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# OUTPUT_DIR still created for pipeline use but NOT publicly mounted
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.include_router(jobs.router)
app.include_router(clips.router)
app.include_router(downloads.router)
app.include_router(channels.router)
app.include_router(feedback.router)
app.include_router(captions.router)
app.include_router(proxy.router)
app.include_router(youtube_metadata.router)
app.include_router(reframe.router)
app.include_router(voice_library.router)

from app.api.routes import debug_reframe, debug_pipeline
app.include_router(debug_reframe.router)
app.include_router(debug_pipeline.router)
app.include_router(progress.router)
app.include_router(director_router)

@app.get("/health")
async def health_check():
    return {
        "ok": True,
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT
    }
