"""
Cast Library — clips grouped by the person they are about.

A guest turns up across several source videos (Dolly Parton has a Letterman
job, a Conan job and a Fallon job), and until now the only way to see their
clips was to remember which jobs they were in. Batches made that worse, since
a batch's jobs never appear in the flat Projects grid at all.

Both endpoints aggregate and filter in Postgres rather than shipping every clip
to the browser: asking for all columns costs ~6.4 kB a row, and the grid needs
about two hundred bytes of it.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.middleware.auth import get_current_user
from app.middleware.roles import is_admin_user
from app.services.supabase_client import get_client

router = APIRouter(prefix="/cast", tags=["cast"])

# Columns the grid and the clip modal actually read. Deliberately omits
# transcript, thinking_steps, rejected_alternatives and the embedding — between
# them they are most of a clip row's weight and none of its display.
_CLIP_FIELDS = (
    "id", "job_id", "channel_id", "clip_index", "main_person",
    "suggested_title", "suggested_description", "hook_text", "content_type",
    "start_time", "end_time", "duration_s",
    "standalone_score", "standalone_result", "quality_notes",
    "clip_strategy_role", "posting_order",
    "stock_review_status", "is_published", "user_approved",
    "thumbnail_path", "thumbnail_wide_path",
    "file_url", "video_reframed_path", "video_captioned_path", "srt_url",
    "created_at",
)

_PUBLISHED = {"all", "published", "unpublished"}
_MARKS = {"all", "unreviewed", "maybe", "rejected", "posted"}
_SORTS = {"newest", "oldest", "score"}


def _require_channel(channel_id: str, user_id: str):
    """Admin-only, and the channel has to be theirs."""
    if not is_admin_user(user_id):
        raise HTTPException(status_code=403, detail="Cast Library is admin only")
    channel_id = (channel_id or "").replace("-", "_")
    if not channel_id:
        raise HTTPException(status_code=400, detail="channel_id is required")
    owned = (
        get_client().table("channels").select("id")
        .eq("id", channel_id).eq("user_id", user_id).execute()
    )
    if not owned.data:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel_id


@router.get("")
async def list_cast(
    channel_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Everyone the channel has ever cut, newest appearance first.

    No pagination: a channel holds fifty to eighty people and each row is a
    name, four numbers and a URL. A person appears here the moment their first
    clip lands — nothing has to be registered in advance.
    """
    channel_id = _require_channel(channel_id, current_user["id"])
    try:
        res = get_client().rpc("cast_library_index", {"p_channel_id": channel_id}).execute()
        return res.data or []
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CastRoute] index error for {channel_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{person}")
async def get_person_clips(
    person: str,
    channel_id: str,
    published: str = Query("all"),
    mark: str = Query("all"),
    sort: str = Query("newest"),
    current_user: dict = Depends(get_current_user),
):
    """One person's clips, across every job they appear in."""
    channel_id = _require_channel(channel_id, current_user["id"])

    if published not in _PUBLISHED:
        raise HTTPException(status_code=400, detail="Invalid published filter")
    if mark not in _MARKS:
        raise HTTPException(status_code=400, detail="Invalid mark filter")
    if sort not in _SORTS:
        raise HTTPException(status_code=400, detail="Invalid sort")

    try:
        res = get_client().rpc("cast_library_clips", {
            "p_channel_id": channel_id,
            "p_person": person,
            "p_published": published,
            "p_mark": mark,
            "p_sort": sort,
        }).execute()
        rows = res.data or []
        if not rows:
            return {"person": person, "clips": []}
        # The function returns whole rows; trim to what the client renders.
        return {
            "person": rows[0].get("main_person") or person,
            "clips": [{k: r.get(k) for k in _CLIP_FIELDS} for r in rows],
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CastRoute] clips error for {person}@{channel_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
