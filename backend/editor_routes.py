# EDITOR MODULE — Isolated module, no dependencies on other project files

import logging
import asyncio
import json
from typing import Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from editor_database import (
    create_editor_job,
    get_editor_job,
    update_editor_job
)
from editor_storage import generate_upload_presigned_url

logger = logging.getLogger("editor.routes")

editor_router = APIRouter(prefix="/api/editor", tags=["editor"])

def process_video_task(job_id: str) -> None:
    from editor_worker import pre_process_video
    pre_process_video.apply_async(args=[job_id], queue="editor")
    logger.info(f"Celery task queued for job {job_id}")

class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str
    user_id: str

@editor_router.post("/upload-url")
async def get_upload_url(request: UploadUrlRequest):
    """
    Creates a job and generates a presigned URL for R2 upload.
    """
    # TODO: Replace request.user_id with FastAPI Dependency Injection: Depends(get_current_user)
    try:
        job_id = await create_editor_job(request.user_id)
        url_info = await generate_upload_presigned_url(request.filename, request.content_type)
        
        # Update job with the expected source r2 key
        await update_editor_job(job_id, source_r2_key=url_info["key"])
        
        return {
            "upload_url": url_info["url"],
            "r2_key": url_info["key"],
            "job_id": job_id
        }
    except Exception as e:
        logger.error(f"Failed to generate upload URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@editor_router.post("/job/{job_id}/start")
async def start_job(job_id: str):
    """
    Starts the processing task for an editor job.
    """
    try:
        job = await get_editor_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
            
        if job.get("status") != "pending":
            raise HTTPException(status_code=400, detail="Job is not in pending state")
            
        await update_editor_job(job_id, status="processing")
        
        # Launch background task via Celery
        process_video_task(job_id)
        
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@editor_router.get("/job/{job_id}")
async def get_job(job_id: str):
    """
    Retrieves the full job dict from editor_jobs.
    """
    try:
        job = await get_editor_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@editor_router.post("/job/{job_id}/auto-edit")
async def auto_edit_job(job_id: str):
    """
    Triggers AI auto-edit analysis for a job.
    """
    try:
        job = await get_editor_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
            
        if job.get("status") != "completed":
            raise HTTPException(status_code=400, detail="Job status must be 'completed' to run auto-edit")
            
        if not job.get("transcript") or len(job.get("transcript", [])) == 0:
            raise HTTPException(status_code=400, detail="Job has no transcript")
            
        await update_editor_job(job_id, status='processing', progress=0)
        
        from editor_worker import auto_edit_task
        auto_edit_task.apply_async(args=[job_id], queue="editor")
        
        return {"job_id": job_id, "message": "Auto edit started"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to queue auto-edit for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@editor_router.get("/job/{job_id}/stream")
async def stream_job(job_id: str):
    """
    Streams job progress via SSE.
    """
    async def event_generator():
        try:
            while True:
                job = await get_editor_job(job_id)
                if not job:
                    yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                    break
                    
                status = job.get("status", "pending")
                progress = job.get("progress", 0)
                
                yield f"data: {json.dumps({'status': status, 'progress': progress})}\n\n"
                
                if status in ["completed", "failed"]:
                    break
                    
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Error streaming job {job_id}: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

class RenderRequest(BaseModel):
    edit_spec: Dict[str, Any]

@editor_router.post("/job/{job_id}/render")
async def render_job(job_id: str, request: RenderRequest):
    """
    Queues a render task for an editor job.
    """
    try:
        job = await get_editor_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
            
        if job.get("status") not in ["completed", "pending"]:
            raise HTTPException(status_code=400, detail="Job status not ready for render")
            
        await update_editor_job(job_id, status='processing', progress=0)
        
        from editor_worker import render_video_task
        render_video_task.apply_async(args=[job_id, request.edit_spec], queue="editor")
        
        return {"job_id": job_id, "message": "Render queued successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to queue render for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@editor_router.post("/job/{job_id}/cancel")
async def cancel_job(job_id: str):
    """
    Cancels an editor job.
    """
    try:
        await update_editor_job(job_id, status="failed", error_message="Cancelled by user")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class BatchRenderRequest(BaseModel):
    job_ids: list[str]
    quality: str

@editor_router.post("/batch-render")
async def batch_render(request: BatchRenderRequest):
    """
    Batch queues multiple editor jobs for rendering.
    """
    try:
        if len(request.job_ids) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 jobs per batch")
            
        queued = []
        skipped = []
        
        from editor_worker import render_video_task
        
        for i, job_id in enumerate(request.job_ids):
            try:
                job = await get_editor_job(job_id)
                if not job:
                    skipped.append({"job_id": job_id, "reason": "Not found"})
                    continue
                    
                if job.get("status") != "completed":
                    skipped.append({"job_id": job_id, "reason": f"Invalid status: {job.get('status')}"})
                    continue
                    
                edit_spec = job.get("edit_spec")
                if not edit_spec:
                    skipped.append({"job_id": job_id, "reason": "No edit_spec"})
                    continue
                    
                spec = dict(edit_spec)
                if "output" not in spec:
                    spec["output"] = {}
                spec["output"]["quality"] = request.quality
                    
                await update_editor_job(job_id, status="processing", progress=0)
                
                # stagger 5s apart to avoid Railway CPU spike
                render_video_task.apply_async(
                    args=[job_id, spec],
                    queue="editor",
                    countdown=i * 5
                )
                queued.append(job_id)
                
            except Exception as e:
                logger.error(f"Failed to queue batch render for job {job_id}: {e}")
                skipped.append({"job_id": job_id, "reason": str(e)})
                
        return {
            "queued": queued,
            "skipped": skipped,
            "total_queued": len(queued)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process batch render: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class JobFromKeyRequest(BaseModel):
    r2_key: str
    user_id: str

@editor_router.post("/job-from-key")
async def job_from_key(request: JobFromKeyRequest):
    """
    Creates an editor job from an existing R2 key.
    """
    try:
        import boto3
        from editor_config import (
            R2_ENDPOINT_URL,
            R2_ACCESS_KEY_ID,
            R2_SECRET_ACCESS_KEY,
            R2_EDITOR_BUCKET_NAME
        )
        
        s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY
        )
        
        try:
            s3_client.head_object(Bucket=R2_EDITOR_BUCKET_NAME, Key=request.r2_key)
        except s3_client.exceptions.ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                raise HTTPException(status_code=404, detail="R2 key not found")
            else:
                raise HTTPException(status_code=400, detail="Cannot verify R2 key")
                
        job_id = await create_editor_job(request.user_id)
        await update_editor_job(job_id, source_r2_key=request.r2_key)
        
        return {
            "job_id": job_id,
            "r2_key": request.r2_key
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create job from key: {e}")
        raise HTTPException(status_code=500, detail=str(e))
