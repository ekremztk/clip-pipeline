from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.services.supabase_client import get_client
from app.pipeline.orchestrator import run_pipeline
from app.models.schemas import SpeakerConfirmRequest

router = APIRouter(prefix="/jobs", tags=["speakers"])

from workers.video_worker import resume_pipeline_from_s04

@router.post("/{job_id}/confirm-speakers")
async def confirm_speakers(job_id: str, request: SpeakerConfirmRequest, background_tasks: BackgroundTasks):
    try:
        supabase = get_client()
        
        # 1. Query jobs table WHERE id = job_id
        job_res = supabase.table("jobs").select("*").eq("id", job_id).execute()
        if not job_res.data:
            raise HTTPException(status_code=404, detail="Job not found")
            
        job = job_res.data[0]
        if job.get("status") != "awaiting_speaker_confirm":
            raise HTTPException(status_code=400, detail="Job is not awaiting speaker confirmation")
            
        # 2. Query transcripts table WHERE job_id = job_id
        transcript_res = supabase.table("transcripts").select("*").eq("job_id", job_id).execute()
        if not transcript_res.data:
            raise HTTPException(status_code=404, detail="Transcript not found")
            
        # 3. Update transcripts table
        # request.speaker_map is a dict of SpeakerInfo, we need to convert it to dict for supabase JSONB
        speaker_map_dict = {k: v.dict() for k, v in request.speaker_map.items()}
        
        supabase.table("transcripts").update({
            "speaker_map": speaker_map_dict,
            "speaker_confirmed": True
        }).eq("job_id", job_id).execute()
        
        # 4. Update jobs table
        supabase.table("jobs").update({
            "status": "processing",
            "current_step": "s04_labeled_transcript"
        }).eq("id", job_id).execute()
        
        # 5. Re-trigger pipeline from s04 onwards
        background_tasks.add_task(resume_pipeline_from_s04, job_id, speaker_map_dict)
        
        # 6. Return
        return {
            "confirmed": True,
            "job_id": job_id,
            "speaker_map": speaker_map_dict
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SpeakersRoute] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
