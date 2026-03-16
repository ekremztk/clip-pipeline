from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
from app.services.supabase_client import get_client

router = APIRouter()

@router.websocket("/ws/jobs/{job_id}/progress")
async def job_progress_ws(websocket: WebSocket, job_id: str):
    await websocket.accept()
    print(f"[WSProgress] Client connected for job {job_id}")
    
    supabase = get_client()
    
    try:
        while True:
            try:
                # Query job state
                response = supabase.table("jobs").select(
                    "status, current_step, current_step_number, progress_pct, error_message, clip_count"
                ).eq("id", job_id).execute()
                
                if not response.data:
                    # Job not found yet or deleted
                    await asyncio.sleep(2)
                    continue
                    
                job_data = response.data[0]
                
                # Send current job state
                state_message = {
                    "job_id": job_id,
                    "status": job_data.get("status"),
                    "current_step": job_data.get("current_step"),
                    "current_step_number": job_data.get("current_step_number"),
                    "progress_pct": job_data.get("progress_pct"),
                    "error_message": job_data.get("error_message"),
                    "clip_count": job_data.get("clip_count")
                }
                
                await websocket.send_json(state_message)
                
                # Check for terminal states
                status = job_data.get("status")
                if status in ("completed", "failed"):
                    print(f"[WSProgress] Job {job_id} reached terminal state: {status}")
                    await websocket.send_json({"event": "done"})
                    await websocket.close()
                    break
                    
            except Exception as e:
                print(f"[WSProgress] DB Error for job {job_id}: {e}")
                await websocket.send_json({"event": "error", "message": str(e)})
                await websocket.close()
                break
                
            await asyncio.sleep(2)
            
    except WebSocketDisconnect:
        print(f"[WSProgress] Client disconnected for job {job_id}")
    except Exception as e:
        print(f"[WSProgress] Unexpected error for job {job_id}: {e}")
        try:
            await websocket.close()
        except:
            pass
