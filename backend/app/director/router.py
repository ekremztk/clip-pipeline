"""Director API Router — chat (SSE), events, memory endpoints."""

import json
import uuid
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.director.agent import run_agent
from app.director.tools.memory import (
    query_memory, save_memory, list_memories, delete_memory,
    get_conversation_history, save_conversation_turn
)
from app.director.tools.database import (
    get_pipeline_stats, get_clip_analysis, get_recent_events
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
    history = get_conversation_history(session_id, last_n=20)
    relevant_memories = query_memory(message, top_k=5)

    # Save user turn
    save_conversation_turn(session_id, "user", message)

    full_response_parts = []

    async for event in run_agent(message, session_id, history, relevant_memories):
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
               .select("*")
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


# ─────────────────────────────────────────────
# Dashboard Aggregation
# ─────────────────────────────────────────────

def _calculate_module_scores(pipeline: dict, clips: dict) -> dict:
    """Calculate simplified module health scores (0-100) from available data."""
    modules = {}

    # Module 1 — Clip Pipeline
    try:
        s = pipeline.get("summary", {})
        total = s.get("total_jobs", 0) or 0
        completed = s.get("completed", 0) or 0
        avg_dur = float(s.get("avg_duration_min", 0) or 0)

        success_rate = (completed / total * 100) if total > 0 else 0

        ca = clips.get("analysis", {})
        total_clips = ca.get("total_clips", 0) or 0
        pass_count = ca.get("pass_count", 0) or 0
        avg_conf = float(ca.get("avg_confidence", 0) or 0)
        pass_rate = (pass_count / total_clips * 100) if total_clips > 0 else 0

        # Score calculation (simplified from DIRECTOR_MODULE.md)
        tech_health = min(20, success_rate * 0.12 + max(0, (12 - avg_dur)) * 0.67)
        ai_quality = min(35, pass_rate * 0.2 + avg_conf * 1.5)
        output_quality = min(25, (total_clips / max(total, 1)) * 3.5)
        score = min(100, round(tech_health + ai_quality + output_quality + 10))

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
            },
        }
    except Exception:
        modules["clip_pipeline"] = {"name": "Clip Pipeline", "score": 0, "status": "KRITIK", "status_color": "red", "metrics": {}}

    # Module 2 — Editor
    modules["editor"] = {
        "name": "Editor",
        "score": 0,
        "status": "VERI YOK",
        "status_color": "gray",
        "metrics": {"note": "Editor metrics will populate with usage data"},
    }

    # Module 3 — Director
    modules["director"] = {
        "name": "Director",
        "score": 0,
        "status": "VERI YOK",
        "status_color": "gray",
        "metrics": {"note": "Director self-assessment requires conversation history"},
    }

    # Overall system health (weighted average of modules with data)
    scored = [m for m in modules.values() if m["score"] > 0]
    overall = round(sum(m["score"] for m in scored) / len(scored)) if scored else 0

    return {"overall_score": overall, "modules": modules}


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

    return result
