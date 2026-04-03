from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.supabase_client import get_client
from app.middleware.auth import verify_token
import asyncio
import json

router = APIRouter()


def _extract_token(websocket: WebSocket) -> str | None:
    """
    Extract bearer token from Sec-WebSocket-Protocol header (format: "bearer.<token>").
    Falls back to query param for backward compatibility, but logs a deprecation warning.
    """
    proto_header = websocket.headers.get("sec-websocket-protocol", "")
    for part in proto_header.split(","):
        part = part.strip()
        if part.startswith("bearer."):
            return part[len("bearer."):]

    # Backward-compatible fallback: query param (logs warning — insecure, remove after frontend updated)
    token = websocket.query_params.get("token")
    if token:
        print("[WSProgress] WARN: token passed as query param — switch to Sec-WebSocket-Protocol header")
    return token


@router.websocket("/ws/jobs/{job_id}/progress")
async def job_progress(websocket: WebSocket, job_id: str):
    token = _extract_token(websocket)

    if not token:
        await websocket.close(code=4001)
        return

    user = await verify_token(token)
    if not user:
        await websocket.close(code=4001)
        return

    # KRIT-2: Verify that this job belongs to the authenticated user
    try:
        supabase = get_client()
        ownership = supabase.table("jobs").select("id").eq("id", job_id).eq("user_id", user["id"]).execute()
        if not ownership.data:
            await websocket.close(code=4003)  # 4003 = Forbidden
            return
    except Exception as e:
        print(f"[WSProgress] Ownership check error for job {job_id}: {e}")
        await websocket.close(code=4011)
        return

    await websocket.accept()
    print(f"[WSProgress] Client connected for job {job_id}")

    disconnected = False

    try:
        while not disconnected:
            try:
                result = supabase.table("jobs").select(
                    "status, current_step, progress_pct, current_step_number"
                ).eq("id", job_id).eq("user_id", user["id"]).execute()

                if not result.data:
                    break

                job = result.data[0]
                payload = {
                    "status": job.get("status"),
                    "current_step": job.get("current_step"),
                    "progress_pct": job.get("progress_pct", 0),
                    "current_step_number": job.get("current_step_number", 0)
                }

                try:
                    await websocket.send_json(payload)
                except Exception:
                    disconnected = True
                    break

                if job.get("status") in ("completed", "failed"):
                    break

            except Exception as e:
                print(f"[WSProgress] DB Error for job {job_id}: {e}")

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        print(f"[WSProgress] Client disconnected for job {job_id}")
    except Exception as e:
        print(f"[WSProgress] Error for job {job_id}: {e}")
    finally:
        print(f"[WSProgress] Connection closed for job {job_id}")
        try:
            await websocket.close()
        except Exception:
            pass
