from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.middleware.auth import get_current_user
from app.pipeline.stock_clip_ai_review import run_stock_clip_ai_review_worker
from app.services.supabase_client import get_client


router = APIRouter(prefix="/stock-reviews", tags=["stock-reviews"])


class StockReviewStartBody(BaseModel):
    channel_id: str
    batch_id: Optional[str] = None
    limit: int = Field(default=25, ge=1, le=500)
    concurrency: int = Field(default=2, ge=1, le=10)
    model: Optional[str] = None


def _normalize_channel_id(channel_id: str) -> str:
    return channel_id.replace("-", "_").strip()


def _ensure_channel_owner(channel_id: str, user_id: str) -> None:
    row = (
        get_client()
        .table("channels")
        .select("id")
        .eq("id", channel_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="Channel not found")


@router.post("/start")
async def start_stock_reviews(
    body: StockReviewStartBody,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    channel_id = _normalize_channel_id(body.channel_id)
    _ensure_channel_owner(channel_id, current_user["id"])
    background_tasks.add_task(
        run_stock_clip_ai_review_worker,
        channel_id,
        current_user["id"],
        body.batch_id,
        body.limit,
        body.concurrency,
        body.model,
    )
    return {
        "ok": True,
        "status": "started",
        "channel_id": channel_id,
        "batch_id": body.batch_id,
        "limit": body.limit,
        "concurrency": body.concurrency,
        "model": body.model,
    }


@router.get("")
async def list_stock_reviews(
    channel_id: str,
    batch_id: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    channel_id = _normalize_channel_id(channel_id)
    _ensure_channel_owner(channel_id, current_user["id"])
    query = (
        get_client()
        .table("stock_clip_ai_reviews")
        .select("*")
        .eq("channel_id", channel_id)
        .eq("user_id", current_user["id"])
        .order("created_at", desc=True)
        .limit(max(1, min(limit, 500)))
    )
    if batch_id:
        query = query.eq("stock_batch_id", batch_id)
    response = query.execute()
    return response.data or []
