"""Director API Router — chat (SSE), events, memory endpoints."""

import json
import uuid
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.director.agent import run_agent
from app.director.message_router import should_use_tools
from app.director.commands import get_commands, find_command, get_command_categories
from app.director.tools.memory import (
    query_memory, save_memory, list_memories, delete_memory,
    get_conversation_history, save_conversation_turn
)
from app.director.tools.database import (
    get_pipeline_stats, get_clip_analysis, get_recent_events, _run_sql,
    get_b4_b5_data, get_cost_breakdown, detect_cost_anomalies
)
from app.services.supabase_client import get_client

router = APIRouter(prefix="/director", tags=["director"])


# ─────────────────────────────────────────────
# Chat (SSE)
# ─────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


async def _sse_generator(message: str, session_id: str) -> AsyncGenerator[str, None]:
    """Wrap agent generator into SSE format."""
    # Detect slash commands — replace with the command's prompt
    actual_message = message
    slash_cmd = None
    if message.strip().startswith("/"):
        slash_cmd = find_command(message.strip().split()[0])
        if slash_cmd:
            # If user typed just the command, use the prompt directly
            # If they typed extra text after it, append it as context
            parts = message.strip().split(maxsplit=1)
            extra = parts[1] if len(parts) > 1 else ""
            actual_message = slash_cmd["prompt"]
            if extra:
                actual_message += f"\n\nEk bilgi: {extra}"

    history = get_conversation_history(session_id, last_n=20)
    relevant_memories = query_memory(actual_message, top_k=5)

    # Save user turn (show original message in history)
    save_conversation_turn(session_id, "user", message)

    full_response_parts = []

    # Slash commands always use tools
    use_tools = True if slash_cmd else should_use_tools(actual_message)
    async for event in run_agent(actual_message, session_id, history, relevant_memories, use_tools=use_tools):
        data = json.dumps(event, ensure_ascii=False)
        yield f"data: {data}\n\n"

        if event.get("type") == "text":
            full_response_parts.append(event.get("text", ""))

    # Save assistant turn
    full_response = "\n".join(full_response_parts)
    if full_response:
        save_conversation_turn(session_id, "assistant", full_response)


@router.post("/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    return StreamingResponse(
        _sse_generator(req.message, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session_id,
        }
    )


# ─────────────────────────────────────────────
# Slash Commands
# ─────────────────────────────────────────────

@router.get("/commands")
async def list_commands():
    """Return all available slash commands for autocomplete."""
    return {"commands": get_commands()}


@router.get("/commands/categories")
async def list_command_categories():
    """Return commands grouped by category."""
    return {"categories": get_command_categories()}


# ─────────────────────────────────────────────
# Memory Endpoints
# ─────────────────────────────────────────────

class MemoryRequest(BaseModel):
    content: str
    type: str
    tags: list[str] = []


@router.get("/memory")
async def list_memories_endpoint(type: str | None = None):
    return list_memories(type)


@router.post("/memory")
async def save_memory_endpoint(req: MemoryRequest):
    memory_id = save_memory(req.content, req.type, req.tags, source="user_instruction")
    return {"id": memory_id}


@router.delete("/memory/{memory_id}")
async def delete_memory_endpoint(memory_id: str):
    success = delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": memory_id}


# ─────────────────────────────────────────────
# Conversation History
# ─────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(limit: int = 20):
    """List past chat sessions with their first message and timestamp."""
    try:
        client = get_client()
        rows = _run_sql("""
            SELECT
                session_id,
                MIN(timestamp) AS started_at,
                MAX(timestamp) AS last_message_at,
                COUNT(*) AS message_count,
                (SELECT content FROM director_conversations c2
                 WHERE c2.session_id = c1.session_id AND c2.role = 'user'
                 ORDER BY timestamp ASC LIMIT 1) AS first_message
            FROM director_conversations c1
            GROUP BY session_id
            ORDER BY MAX(timestamp) DESC
            LIMIT %s
        """, (limit,))
        return {"sessions": rows}
    except Exception as e:
        return {"sessions": [], "error": str(e)}


@router.get("/conversations/{session_id}")
async def get_session_history(session_id: str, limit: int = 50):
    return get_conversation_history(session_id, last_n=limit)


# ─────────────────────────────────────────────
# Dashboard Data
# ─────────────────────────────────────────────

@router.get("/stats")
async def pipeline_stats(days: int = 7, channel_id: str | None = None):
    return get_pipeline_stats(days, channel_id)


@router.get("/clips")
async def clip_stats(days: int = 7, job_id: str | None = None):
    return get_clip_analysis(job_id, days)


@router.get("/events")
async def recent_events(module: str | None = None, days: int = 7, limit: int = 50):
    return get_recent_events(module, days, limit)


# ─────────────────────────────────────────────
# Event Ingestion (from pipeline hooks)
# ─────────────────────────────────────────────

class EventRequest(BaseModel):
    module_name: str
    event_type: str
    payload: dict
    session_id: str | None = None
    channel_id: str | None = None


@router.post("/events")
async def ingest_event(req: EventRequest):
    try:
        client = get_client()
        client.table("director_events").insert({
            "module_name": req.module_name,
            "event_type": req.event_type,
            "payload": req.payload,
            "session_id": req.session_id,
            "channel_id": req.channel_id,
        }).execute()

        # Cross-module signal: editor opened a clip → M2 → M1 feedback signal
        if req.event_type == "clip_opened_in_editor":
            try:
                client.table("director_cross_module_signals").insert({
                    "signal_type": "clip_opened_in_editor",
                    "source_module": "module_2",
                    "target_module": "module_1",
                    "payload": req.payload,
                    "channel_id": req.channel_id,
                }).execute()
            except Exception:
                pass  # non-critical

        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# Recommendations
# ─────────────────────────────────────────────

@router.get("/recommendations")
async def get_recommendations(status: str = "pending", limit: int = 20):
    try:
        client = get_client()
        res = (client.table("director_recommendations")
               .select("id,module_name,title,description,priority,impact,effort,status,metadata,created_at")
               .eq("status", status)
               .order("priority", desc=False)
               .limit(limit)
               .execute())
        return res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RecommendationUpdate(BaseModel):
    status: str
    dismissed_reason: str | None = None


@router.patch("/recommendations/{rec_id}")
async def update_recommendation(rec_id: str, req: RecommendationUpdate):
    try:
        client = get_client()
        update_data: dict = {"status": req.status}
        if req.dismissed_reason:
            update_data["dismissed_reason"] = req.dismissed_reason
        client.table("director_recommendations").update(update_data).eq("id", rec_id).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommendations/{rec_id}/dismiss")
async def dismiss_recommendation(rec_id: str):
    """Dismiss a recommendation and mark it as dismissed."""
    try:
        client = get_client()
        client.table("director_recommendations").update({
            "status": "dismissed"
        }).eq("id", rec_id).execute()
        return {"ok": True, "dismissed": rec_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommendations/{rec_id}/apply")
async def apply_recommendation(rec_id: str, note: str = ""):
    """Mark a recommendation as applied."""
    try:
        client = get_client()
        client.table("director_recommendations").update({
            "status": "applied",
            "dismissed_reason": note or None,
        }).eq("id", rec_id).execute()
        return {"ok": True, "applied": rec_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup-recommendations")
async def cleanup_stale_recommendations():
    """Archive recommendations pending for 30+ days."""
    try:
        rows = _run_sql("""
            UPDATE director_recommendations
            SET status = 'archived'
            WHERE status = 'pending'
              AND created_at < now() - interval '30 days'
            RETURNING id
        """)
        return {"archived": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cross-module-graph")
async def get_cross_module_graph(channel_id: str = None, days: int = 7):
    """Return cross-module signal flow for dependency visualization."""
    try:
        from app.director.dependency_graph import get_cross_module_signals, get_full_dependency_map
        signals = get_cross_module_signals(channel_id, days)
        dep_map = get_full_dependency_map()
        return {"signals": signals, "dependency_map": dep_map}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# Dashboard Aggregation
# ─────────────────────────────────────────────

def _calculate_module_scores(pipeline: dict, clips: dict) -> dict:
    """Calculate module health scores (0-100). Returns None score when no data."""
    modules = {}

    # Module 1 — Clip Pipeline
    try:
        s = pipeline.get("summary", {})
        total = int(s.get("total_jobs", 0) or 0)
        completed = int(s.get("completed", 0) or 0)
        avg_dur = float(s.get("avg_duration_min", 0) or 0)

        ca = clips.get("analysis", {})
        total_clips = int(ca.get("total_clips", 0) or 0)
        pass_count = int(ca.get("pass_count", 0) or 0)
        avg_conf = float(ca.get("avg_confidence", 0) or 0)

        if total == 0 and total_clips == 0:
            # No data yet — do not fabricate a score
            modules["clip_pipeline"] = {
                "name": "Clip Pipeline",
                "score": None,
                "status": "VERI YOK",
                "status_color": "gray",
                "metrics": {},
                "subscores": {},
            }
        else:
            success_rate = (completed / total * 100) if total > 0 else 0
            pass_rate = (pass_count / total_clips * 100) if total_clips > 0 else 0

            # Boyut 1: Teknik Sağlık (max 20)
            sr_score = 6 if success_rate >= 100 else 5 if success_rate >= 95 else 4 if success_rate >= 90 else 2 if success_rate >= 80 else 0
            dur_score = 4 if avg_dur < 6 else 3 if avg_dur < 8 else 2 if avg_dur < 12 else 0
            tech_health = sr_score + dur_score + 5  # +5 base (R2 upload, fallback assume ok)

            # Boyut 2: AI Karar Kalitesi (max 35)
            pr_score = 8 if pass_rate > 50 else 6 if pass_rate > 35 else 3 if pass_rate > 20 else 0
            conf_score = 7 if avg_conf >= 8.0 else 5 if avg_conf >= 7.0 else 3 if avg_conf >= 6.0 else 0
            ai_quality = pr_score + conf_score + 5  # +5 base

            # Boyut 3: Çıktı Kalitesi (max 25)
            clips_per_job = total_clips / max(total, 1)
            cj_score = 8 if clips_per_job >= 5 else 5 if clips_per_job >= 3 else 2 if clips_per_job >= 1 else 0
            output_quality = cj_score + 8  # +8 base

            # Boyut 4+5: Öğrenme (max 15) + Stratejik Olgunluk (max 5)
            b4b5_detail: dict = {}
            if total < 5:
                learning, strategic = 8, 3  # no data yet — neutral
            else:
                try:
                    b4b5 = get_b4_b5_data()
                    learning = b4b5.get("b4", 8)
                    strategic = b4b5.get("b5", 3)
                    b4b5_detail = {"b4_detail": b4b5.get("b4_detail", {}),
                                   "b5_detail": b4b5.get("b5_detail", {})}
                except Exception:
                    learning, strategic = 8, 3

            learn_strategy = learning + strategic  # max 20

            score = min(100, round(tech_health + ai_quality + output_quality + learn_strategy))

            if score >= 85:
                status, status_color = "GUCLU", "green"
            elif score >= 71:
                status, status_color = "IYI", "cyan"
            elif score >= 56:
                status, status_color = "ORTA", "yellow"
            elif score >= 36:
                status, status_color = "ZAYIF", "orange"
            else:
                status, status_color = "KRITIK", "red"

            modules["clip_pipeline"] = {
                "name": "Clip Pipeline",
                "score": score,
                "status": status,
                "status_color": status_color,
                "metrics": {
                    "success_rate": round(success_rate, 1),
                    "avg_duration_min": avg_dur,
                    "total_jobs": total,
                    "pass_rate": round(pass_rate, 1),
                    "avg_confidence": avg_conf,
                    "total_clips": total_clips,
                    **b4b5_detail,
                },
                "subscores": {
                    "teknik_saglik": {"score": tech_health, "max": 20},
                    "ai_karar_kalitesi": {"score": ai_quality, "max": 35},
                    "cikti_kalitesi": {"score": output_quality, "max": 25},
                    "ogrenme": {"score": learning, "max": 15},
                    "stratejik_olgunluk": {"score": strategic, "max": 5},
                },
            }
    except Exception:
        modules["clip_pipeline"] = {
            "name": "Clip Pipeline", "score": None, "status": "HATA",
            "status_color": "red", "metrics": {}, "subscores": {},
        }

    # Module 2 — Editor
    modules["editor"] = {
        "name": "Editor",
        "score": None,
        "status": "VERI YOK",
        "status_color": "gray",
        "metrics": {},
        "subscores": {},
    }

    # Module 3 — Director
    modules["director"] = {
        "name": "Director",
        "score": None,
        "status": "VERI YOK",
        "status_color": "gray",
        "metrics": {},
        "subscores": {},
    }

    scored = [m for m in modules.values() if m.get("score") is not None]
    overall = round(sum(m["score"] for m in scored) / len(scored)) if scored else None

    return {"overall_score": overall, "modules": modules}


# ─────────────────────────────────────────────
# Health Pulse — in-memory cache, updated every 5 min by background task
# ─────────────────────────────────────────────

_health_pulse_cache: dict = {}


def _compute_health_pulse() -> dict:
    """Compute health pulse synchronously. Called by scheduler and endpoint."""
    from datetime import datetime, timezone
    try:
        client = get_client()

        # 1. Pipeline success rate (last 7 days)
        pipeline_sql = """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed
            FROM jobs
            WHERE created_at > now() - interval '7 days'
        """
        pipeline_rows = _run_sql(pipeline_sql)
        ps = pipeline_rows[0] if pipeline_rows else {}
        total_jobs = int(ps.get("total", 0) or 0)
        success_rate = (int(ps.get("completed", 0) or 0) / total_jobs * 100) if total_jobs > 0 else None

        # 2. Avg clip confidence (last 7 days)
        clip_sql = """
            SELECT ROUND(AVG(overall_confidence)::NUMERIC, 2) AS avg_conf
            FROM clips WHERE created_at > now() - interval '7 days'
        """
        clip_rows = _run_sql(clip_sql)
        avg_conf = float((clip_rows[0] or {}).get("avg_conf") or 0)

        # 3. Open critical recommendations
        crit_res = (client.table("director_recommendations")
                    .select("id", count="exact")
                    .eq("status", "pending").lte("priority", 2).execute())
        open_criticals = crit_res.count or 0

        # 4. Cost anomaly
        try:
            anomaly_list = detect_cost_anomalies(2.0)
            cost_anomaly_count = len(anomaly_list)
        except Exception:
            anomaly_list = []
            cost_anomaly_count = 0

        # 5. Recent pipeline failures (last 24h)
        fail_sql = """
            SELECT COUNT(*) AS failed
            FROM jobs
            WHERE created_at > now() - interval '1 day' AND status = 'failed'
        """
        fail_rows = _run_sql(fail_sql)
        recent_failures = int((fail_rows[0] or {}).get("failed", 0) or 0)

        # Compute weighted score
        checks = {}
        weighted_sum = 0.0
        total_weight = 0.0

        if success_rate is not None:
            sr_score = 100 if success_rate >= 95 else 80 if success_rate >= 85 else 60 if success_rate >= 70 else 30
            checks["pipeline_success_rate"] = {"value": round(success_rate, 1), "score": sr_score, "weight": 0.30}
            weighted_sum += sr_score * 0.30; total_weight += 0.30

        if avg_conf > 0:
            conf_score = 100 if avg_conf >= 8.0 else 80 if avg_conf >= 7.0 else 60 if avg_conf >= 6.0 else 30
            checks["avg_clip_confidence"] = {"value": float(avg_conf), "score": conf_score, "weight": 0.20}
            weighted_sum += conf_score * 0.20; total_weight += 0.20

        crit_score = 100 if open_criticals == 0 else 60 if open_criticals <= 2 else 20
        checks["open_critical_issues"] = {"value": open_criticals, "score": crit_score, "weight": 0.20}
        weighted_sum += crit_score * 0.20; total_weight += 0.20

        cost_score = 80 if cost_anomaly_count > 0 else 100
        checks["cost_anomaly"] = {"value": cost_anomaly_count, "score": cost_score, "weight": 0.15}
        weighted_sum += cost_score * 0.15; total_weight += 0.15

        fail_score = 100 if recent_failures == 0 else 60 if recent_failures <= 2 else 20
        checks["recent_failures_24h"] = {"value": recent_failures, "score": fail_score, "weight": 0.15}
        weighted_sum += fail_score * 0.15; total_weight += 0.15

        overall = round(weighted_sum / total_weight) if total_weight > 0 else None

        if overall is None:
            status, color = "VERI YOK", "gray"
        elif overall >= 85:
            status, color = "GUCLU", "green"
        elif overall >= 71:
            status, color = "IYI", "cyan"
        elif overall >= 56:
            status, color = "ORTA", "yellow"
        elif overall >= 36:
            status, color = "ZAYIF", "orange"
        else:
            status, color = "KRITIK", "red"

        return {
            "score": overall,
            "status": status,
            "status_color": color,
            "checks": checks,
            "gemini_used": False,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        print(f"[HealthPulse] compute error: {e}")
        return {"score": None, "status": "HATA", "status_color": "red",
                "checks": {}, "gemini_used": False,
                "last_updated": datetime.now(timezone.utc).isoformat()}


@router.get("/health-pulse")
async def health_pulse():
    """Serve from in-memory cache (updated every 5 min). Falls back to live compute."""
    if _health_pulse_cache:
        return _health_pulse_cache
    # Cache empty (first request before scheduler fires) — compute live
    import asyncio
    result = await asyncio.get_event_loop().run_in_executor(None, _compute_health_pulse)
    _health_pulse_cache.update(result)
    return result


@router.get("/analyses")
async def get_analyses(module: str | None = None, limit: int = 20):
    """Analysis history from director_analyses table."""
    try:
        client = get_client()
        q = (client.table("director_analyses")
             .select("id,module_name,triggered_by,score,subscores,findings,data_points_used,timestamp")
             .order("timestamp", desc=True)
             .limit(limit))
        if module:
            q = q.eq("module_name", module)
        res = q.execute()
        return res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/costs")
async def cost_breakdown(days: int = 30, per: str = "day"):
    """Cost breakdown from pipeline_audit_log.token_usage. per: day|step|job."""
    try:
        return get_cost_breakdown(days, per)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/costs/anomalies")
async def cost_anomalies(sigma: float = 2.0):
    """Jobs with cost outside 2σ (or custom sigma) threshold."""
    try:
        return detect_cost_anomalies(sigma)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-analysis")
async def run_analysis(module: str = "all", triggered_by: str = "cron"):
    """Trigger a system analysis — for Railway cron or manual call."""
    try:
        from app.director.tools.database import get_pipeline_stats, get_clip_analysis
        pipeline = get_pipeline_stats(30)
        clips = get_clip_analysis(None, 30)
        scores = _calculate_module_scores(pipeline, clips)

        client = get_client()
        analysis_row = {
            "module_name": module,
            "triggered_by": triggered_by,
            "score": scores.get("overall_score") or 0,
            "subscores": scores.get("modules", {}),
            "findings": [
                {"key": "pipeline_summary", "data": pipeline.get("summary", {})},
                {"key": "clip_summary", "data": clips.get("analysis", {})},
            ],
            "recommendations": [],
            "data_points_used": int((pipeline.get("summary") or {}).get("total_jobs", 0) or 0),
        }
        res = client.table("director_analyses").insert(analysis_row).execute()
        analysis_id = res.data[0].get("id") if res.data else None

        return {
            "ok": True,
            "analysis_id": analysis_id,
            "overall_score": scores.get("overall_score"),
            "triggered_by": triggered_by,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard")
async def dashboard_aggregate(days: int = 7):
    """Single endpoint returning all dashboard data."""
    result: dict = {"period_days": days}

    # Pipeline stats
    try:
        result["pipeline"] = get_pipeline_stats(days)
    except Exception:
        result["pipeline"] = {"error": "unavailable"}

    # Clip analysis
    try:
        result["clips"] = get_clip_analysis(None, days)
    except Exception:
        result["clips"] = {"error": "unavailable"}

    # AI Costs (Langfuse)
    try:
        from app.director.tools.langfuse import get_langfuse_data
        result["costs_ai"] = get_langfuse_data(None, days)
    except Exception:
        result["costs_ai"] = {"error": "unavailable"}

    # Deepgram Costs
    try:
        from app.director.tools.deepgram import get_deepgram_usage
        result["costs_deepgram"] = get_deepgram_usage(days)
    except Exception:
        result["costs_deepgram"] = {"error": "unavailable"}

    # Recommendations
    try:
        client = get_client()
        recs = (client.table("director_recommendations")
                .select("*")
                .eq("status", "pending")
                .order("priority", desc=False)
                .limit(10)
                .execute())
        result["recommendations"] = recs.data or []
    except Exception:
        result["recommendations"] = []

    # Sentry Errors
    try:
        from app.director.tools.sentry import get_sentry_issues
        result["errors"] = get_sentry_issues(days)
    except Exception:
        result["errors"] = []

    # Recent Events
    try:
        result["events"] = get_recent_events(None, days, 20)
    except Exception:
        result["events"] = []

    # Module Scores
    result["modules"] = _calculate_module_scores(
        result.get("pipeline", {}),
        result.get("clips", {}),
    )

    # Cost breakdown (last N days)
    try:
        result["costs_pipeline"] = get_cost_breakdown(days, "day")
    except Exception:
        result["costs_pipeline"] = {"error": "unavailable"}

    # Cost anomalies
    try:
        result["cost_anomalies"] = detect_cost_anomalies()
    except Exception:
        result["cost_anomalies"] = []

    # Health pulse (from cache or live)
    try:
        result["health_pulse"] = _health_pulse_cache if _health_pulse_cache else _compute_health_pulse()
    except Exception:
        result["health_pulse"] = {}

    # Latest analysis
    try:
        client = get_client()
        latest_analysis = (client.table("director_analyses")
                           .select("id,score,timestamp,triggered_by")
                           .order("timestamp", desc=True).limit(1).execute())
        result["latest_analysis"] = latest_analysis.data[0] if latest_analysis.data else None
    except Exception:
        result["latest_analysis"] = None

    return result


# ─────────────────────────────────────────────
# Decision Journal
# ─────────────────────────────────────────────

class DecisionRequest(BaseModel):
    decision: str
    context: str | None = None
    alternatives: list[str] | None = None
    expected_impact: str | None = None
    channel_id: str | None = None
    related_rec_id: str | None = None


@router.get("/decisions")
async def list_decisions(channel_id: str | None = None, limit: int = 50):
    """Fetch decision journal entries."""
    try:
        client = get_client()
        q = (client.table("director_decision_journal")
             .select("*")
             .order("timestamp", desc=True)
             .limit(limit))
        if channel_id:
            q = q.eq("channel_id", channel_id)
        res = q.execute()
        return res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decisions")
async def create_decision(req: DecisionRequest):
    """Record a new decision in the journal."""
    try:
        client = get_client()
        row = {
            "decision": req.decision,
            "context": req.context,
            "alternatives": req.alternatives or [],
            "expected_impact": req.expected_impact,
            "status": "active",
        }
        if req.channel_id:
            row["channel_id"] = req.channel_id
        if req.related_rec_id:
            row["related_rec_id"] = req.related_rec_id
        res = client.table("director_decision_journal").insert(row).execute()
        return res.data[0] if res.data else {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DecisionOutcome(BaseModel):
    actual_impact: str
    status: str = "evaluated"


@router.patch("/decisions/{decision_id}/outcome")
async def update_decision_outcome(decision_id: str, req: DecisionOutcome):
    """Record actual impact after a decision was made."""
    try:
        from datetime import datetime, timezone
        client = get_client()
        client.table("director_decision_journal").update({
            "actual_impact": req.actual_impact,
            "status": req.status,
            "measured_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", decision_id).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# Prompt Lab
# ─────────────────────────────────────────────

class PromptLabEntry(BaseModel):
    name: str
    module_name: str
    step: str
    prompt_text: str
    notes: str | None = None


@router.get("/prompt-lab")
async def list_prompts(module_name: str | None = None, step: str | None = None):
    """List all prompt lab entries."""
    try:
        client = get_client()
        q = client.table("director_prompt_lab").select("*").order("module_name").order("step").order("version", desc=True)
        if module_name:
            q = q.eq("module_name", module_name)
        if step:
            q = q.eq("step", step)
        res = q.execute()
        return res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompt-lab")
async def create_prompt(req: PromptLabEntry):
    """Save a prompt variant to the lab."""
    try:
        client = get_client()
        # Get next version for this module+step
        existing = (client.table("director_prompt_lab")
                    .select("version")
                    .eq("module_name", req.module_name)
                    .eq("step", req.step)
                    .order("version", desc=True)
                    .limit(1)
                    .execute())
        next_version = (existing.data[0]["version"] + 1) if existing.data else 1
        res = client.table("director_prompt_lab").insert({
            "name": req.name,
            "module_name": req.module_name,
            "step": req.step,
            "prompt_text": req.prompt_text,
            "version": next_version,
            "notes": req.notes,
            "is_active": False,
        }).execute()
        return res.data[0] if res.data else {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompt-lab/{prompt_id}/activate")
async def activate_prompt(prompt_id: str):
    """Mark a prompt as active (deactivates others for same module+step)."""
    try:
        client = get_client()
        # Get the prompt to find its module+step
        entry = client.table("director_prompt_lab").select("module_name,step").eq("id", prompt_id).single().execute()
        if not entry.data:
            raise HTTPException(status_code=404, detail="Prompt not found")
        # Deactivate all others for this module+step
        client.table("director_prompt_lab").update({"is_active": False}).eq(
            "module_name", entry.data["module_name"]
        ).eq("step", entry.data["step"]).execute()
        # Activate this one
        client.table("director_prompt_lab").update({"is_active": True}).eq("id", prompt_id).execute()
        return {"ok": True, "activated": prompt_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
