from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
import httpx
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/proxy", tags=["proxy"])

# Only allow proxying from our own R2 bucket domain
ALLOWED_HOSTS = [
    "pub-d053d45c7ff247899fd656863e5d9839.r2.dev",
]


@router.get("/clip")
async def proxy_clip(url: str = Query(..., description="R2 clip URL to proxy"), current_user: dict = Depends(get_current_user)):
    """
    Proxies a clip file from R2 storage to bypass browser CORS restrictions.
    Only allows requests to whitelisted R2 hosts.
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.hostname not in ALLOWED_HOSTS:
            raise HTTPException(status_code=403, detail="URL host not allowed")

        async def stream():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("GET", url) as r:
                    r.raise_for_status()
                    async for chunk in r.aiter_bytes(chunk_size=65536):
                        yield chunk

        # Peek at headers first to get content-type and length
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
        print(f"[Proxy] Error proxying {url}: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch clip from storage")
