from dotenv import load_dotenv

# Load .env variables at the top
load_dotenv()

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

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


async def _daily_analysis_scheduler():
    """Daily 03:00 UTC: run full analysis. Weekly Monday 09:00 UTC: weekly digest."""
    import asyncio
    from datetime import datetime, timezone
    await asyncio.sleep(120)  # wait 2 min after startup
    while True:
        try:
            now = datetime.now(timezone.utc)
            # Daily at 03:00 UTC
            if now.hour == 3 and now.minute < 5:
                await asyncio.get_event_loop().run_in_executor(
                    None, _run_daily_analysis
                )
            # Weekly digest: Monday (weekday=0) at 09:00 UTC
            if now.weekday() == 0 and now.hour == 9 and now.minute < 5:
                await asyncio.get_event_loop().run_in_executor(
                    None, _run_weekly_digest
                )
        except Exception as e:
            print(f"[DailyScheduler] error: {e}")
        await asyncio.sleep(300)  # check every 5 minutes


def _run_daily_analysis():
    """Synchronous: trigger full analysis and proactive checks."""
    try:
        import requests
        import os
        base = os.getenv("RAILWAY_STATIC_URL", "http://localhost:8000")
        requests.post(f"{base}/director/run-analysis",
                      params={"module": "all", "triggered_by": "scheduled"}, timeout=30)
        from app.director.proactive import run_proactive_checks
        run_proactive_checks()
        print("[DailyAnalysis] Completed")
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
    pulse_task = asyncio.create_task(_health_pulse_scheduler())
    proactive_task = asyncio.create_task(_proactive_scheduler())
    daily_task = asyncio.create_task(_daily_analysis_scheduler())
    yield
    # Cleanup Director connection pool
    try:
        from app.director.tools.database import _connection_pool
        if _connection_pool and not _connection_pool.closed:
            _connection_pool.closeall()
            print("[DB] Director connection pool closed.")
    except Exception:
        pass
    for task in [pulse_task, proactive_task, daily_task]:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

from app.api.routes import jobs, clips, speakers, downloads, channels, feedback, captions, proxy, youtube_metadata, reframe
from app.api.websocket import progress
from app.director.router import router as director_router

app = FastAPI(
    title="Prognot Clip Pipeline",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure OUTPUT_DIR exists before mounting to prevent StaticFiles from throwing RuntimeError
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(settings.OUTPUT_DIR)), name="output")

app.include_router(jobs.router)
app.include_router(clips.router)
app.include_router(speakers.router)
app.include_router(downloads.router)
app.include_router(channels.router)
app.include_router(feedback.router)
app.include_router(captions.router)
app.include_router(proxy.router)
app.include_router(youtube_metadata.router)
app.include_router(reframe.router)
app.include_router(progress.router)
app.include_router(director_router)

@app.get("/health")
async def health_check():
    return {
        "ok": True,
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT
    }
