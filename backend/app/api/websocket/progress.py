from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.supabase_client import get_client
import asyncio
import json

router = APIRouter()

@router.websocket("/ws/jobs/{job_id}/progress")
async def job_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    print(f"[WSProgress] Client connected for job {job_id}")
    
    disconnected = False
    
    try:
        while not disconnected:
            try:
                supabase = get_client()
                result = supabase.table("jobs").select(
                    "status, current_step, progress_pct, current_step_number"
                ).eq("id", job_id).execute()
                
                if not result.data:
                    break
                    
                if result.data:
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
                    
                    # Stop polling if job is in terminal state
                    if job.get("status") in ("completed", "failed", "awaiting_speaker_confirm"):
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
