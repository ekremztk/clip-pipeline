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
