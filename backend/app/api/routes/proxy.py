from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from urllib.parse import urlparse
import re
import httpx
from app.middleware.auth import get_current_user
from app.services.supabase_client import get_client

router = APIRouter(prefix="/proxy", tags=["proxy"])

# Only allow proxying from our own R2 bucket domain
ALLOWED_HOSTS = [
    "pub-d053d45c7ff247899fd656863e5d9839.r2.dev",
]

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _verify_ownership(url: str, clip_id: str | None, user_id: str) -> None:
    """
    Verify the authenticated user owns the clip behind this R2 URL.

    New clips: URL path is like `captions/<uuid>.mp4` or `reframe/<uuid>.mp4`
    → require clip_id query param, look up clip.job_id, match user.

    Legacy clips: URL path is `<job_id>/<filename>` (S08 exports from the
    pre-Modal era) → fall back to matching the first path segment as job_id.
    """
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_HOSTS:
        raise HTTPException(status_code=403, detail="URL host not allowed")

    sb = get_client()

    # Preferred path: clip_id lookup (works for captions/ and reframe/ URLs)
    if clip_id:
        clip_row = (
            sb.table("clips")
            .select("job_id")
            .eq("id", clip_id)
            .limit(1)
            .execute()
        )
        if not clip_row.data:
            raise HTTPException(status_code=404, detail="Clip not found")
        job_id = clip_row.data[0].get("job_id")
        if not job_id:
            raise HTTPException(status_code=403, detail="Access denied")
        job_row = (
            sb.table("jobs")
            .select("id")
            .eq("id", job_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not job_row.data:
            raise HTTPException(status_code=403, detail="Access denied")
        return

    # Legacy fallback: <job_id>/<filename> (S08-only exports)
    path_parts = parsed.path.strip("/").split("/")
    if path_parts and _UUID_RE.match(path_parts[0]):
        legacy_job_id = path_parts[0]
        job_row = (
            sb.table("jobs")
            .select("id")
            .eq("id", legacy_job_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if job_row.data:
            return

    raise HTTPException(status_code=403, detail="Access denied")


@router.get("/clip")
async def proxy_clip(
    url: str = Query(..., description="R2 clip URL to proxy"),
    clip_id: str | None = Query(None, description="Clip ID for ownership check"),
    current_user: dict = Depends(get_current_user),
):
    """
    Proxies a clip file from R2 storage.
    Validates: (1) host whitelist, (2) ownership via clip_id (or legacy path-based).
    """
    try:
        _verify_ownership(url, clip_id, current_user["id"])

        async def stream():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("GET", url) as r:
                    r.raise_for_status()
                    async for chunk in r.aiter_bytes(chunk_size=65536):
                        yield chunk

        async with httpx.AsyncClient(timeout=30) as client:
            head = await client.head(url)

        content_type = head.headers.get("content-type", "video/mp4")
        content_length = head.headers.get("content-length")

        headers = {"Accept-Ranges": "bytes"}
        if content_length:
            headers["Content-Length"] = content_length

        return StreamingResponse(
            stream(),
            media_type=content_type,
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Proxy] Error proxying clip: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch clip from storage")
