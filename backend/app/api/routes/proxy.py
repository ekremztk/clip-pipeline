from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from urllib.parse import urlparse
import httpx
from app.middleware.auth import get_current_user
from app.services.supabase_client import get_client

router = APIRouter(prefix="/proxy", tags=["proxy"])

# Only allow proxying from our own R2 bucket domain
ALLOWED_HOSTS = [
    "pub-d053d45c7ff247899fd656863e5d9839.r2.dev",
]


@router.get("/clip")
async def proxy_clip(
    url: str = Query(..., description="R2 clip URL to proxy"),
    current_user: dict = Depends(get_current_user)
):
    """
    Proxies a clip file from R2 storage.
    Validates: (1) host whitelist, (2) job ownership via user_id.
    """
    try:
        parsed = urlparse(url)

        # (1) Host whitelist check
        if parsed.hostname not in ALLOWED_HOSTS:
            raise HTTPException(status_code=403, detail="URL host not allowed")

        # (2) YÜKS-1: Ownership check — extract job_id from path: /<job_id>/<filename>
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) >= 1:
            job_id = path_parts[0]
            supabase = get_client()
            job_check = supabase.table("jobs").select("id").eq("id", job_id).eq("user_id", current_user["id"]).execute()
            if not job_check.data:
                raise HTTPException(status_code=403, detail="Access denied")

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
