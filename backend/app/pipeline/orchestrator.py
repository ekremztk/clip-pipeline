from datetime import datetime, timezone
import time
import os
import traceback

from app.config import settings
from app.services.supabase_client import get_client
from app.models.enums import JobStatus, StepStatus
from app.services import storage


def update_job(job_id: str, **kwargs) -> None:
    """
    Updates jobs table in Supabase with given kwargs.
    Accepted fields: status, current_step, current_step_number, progress_pct, 
    clip_count, error_message, started_at, completed_at
    """
    try:
        supabase = get_client()
        valid_fields = {
            "status", "current_step", "current_step_number", "progress_pct",
            "clip_count", "error_message", "started_at", "completed_at"
        }
        update_data = {k: v for k, v in kwargs.items() if k in valid_fields}
        
        if not update_data:
            return
            
        supabase.table("jobs").update(update_data).eq("id", job_id).execute()
        print(f"[Orchestrator] Updated job {job_id} with {update_data}")
    except Exception as e:
        print(f"[Orchestrator] Error updating job {job_id}: {e}")


from app.utils.audit_logger import log_pipeline_step

def log_step(job_id: str, step_number: int, step_name: str, status: str,
             input_summary: dict | None = None, output_summary: dict | None = None,
             duration_ms: int | None = None, error_message: str | None = None) -> None:
    """
    Inserts a row into pipeline_audit_log table.
    Delegates to audit_logger.py
    """
    log_pipeline_step(
        job_id=job_id,
        step_number=step_number,
        step_name=step_name,
        status=status,
        input_summary=input_summary,
        output_summary=output_summary,
        duration_ms=duration_ms,
        error_message=error_message
    )


def run_pipeline(job_id: str, video_path: str, video_title: str,
                 guest_name: str | None = None, channel_id: str = "speedy_cast") -> None:
    """
    Main pipeline function called by the worker.
    Runs steps exactly as defined.
    """
    audio_path = None
    try:
        started_at = datetime.now(timezone.utc).isoformat()
        update_job(
            job_id=job_id,
            status=JobStatus.PROCESSING.value,
            started_at=started_at,
            current_step_number=0,
            progress_pct=0,
            current_step="initializing"
        )
        
        steps = [
            (1, "s01_audio_extract", 10),
            (2, "s02_transcribe", 20),
            (3, "s03_speaker_id", 28),
            (4, "s04_labeled_transcript", 36),
            (5, "s05_energy_map", 44),
            (6, "s06_video_analysis", 52),
            (7, "s07_context_build", 58),
            (8, "s07b_humor_map", 64),
            (9, "s07c_signal_fusion", 70),
            (10, "s08_clip_finder", 80),
            (11, "s09_quality_gate", 88),
            (12, "s09b_clip_strategy", 92),
            (13, "s10_precision_cut", 96),
            (14, "s11_export", 100)
        ]
        
        # State variables to pass between steps
        transcript_data = None
        speaker_data = None
        labeled_transcript = None
        energy_data = None
        visual_events = None
        context = None
        channel_dna = {}
        humor_moments = None
        fused_timeline = None
        
        for step_number, step_name, progress_pct in steps:
            step_start_time = time.time()
            log_step(job_id, step_number, step_name, StepStatus.STARTED.value)
            
            update_job(
                job_id=job_id,
                current_step=step_name,
                current_step_number=step_number,
                progress_pct=progress_pct
            )
            
            try:
                if step_number == 1:
                    from app.pipeline.steps import s01_audio_extract
                    audio_path = s01_audio_extract.run(video_path, job_id)
                elif step_number == 2:
                    from app.pipeline.steps import s02_transcribe
                    transcript_data = s02_transcribe.run(audio_path, job_id)
                elif step_number == 3:
                    from app.pipeline.steps import s03_speaker_id
                    speaker_data = s03_speaker_id.run(transcript_data, job_id)
                    
                    supabase = get_client()
                    transcript_raw = transcript_data.get("raw_response", {}) if isinstance(transcript_data, dict) else {}
                    words = transcript_data.get("words", []) if isinstance(transcript_data, dict) else []
                    s_map = speaker_data.get("predicted_map", {}) if isinstance(speaker_data, dict) else {}

                    supabase.table("transcripts").upsert({
                        "job_id": job_id,
                        "raw_response": transcript_raw,
                        "labeled_transcript": "",
                        "word_timestamps": words,
                        "speaker_map": s_map,
                        "speaker_confirmed": False
                    }).execute()
                    
                    update_job(job_id=job_id, status="awaiting_speaker_confirm")
                    # Pipeline pauses here — resumes after /confirm-speakers
                    print(f"[Orchestrator] Job {job_id} paused — awaiting speaker confirmation")
                    return  # Stop execution, wait for resume_pipeline_from_s04
                elif step_number == 4:
                    from app.pipeline.steps import s04_labeled_transcript
                    predicted_map = speaker_data.get("predicted_map", {}) if speaker_data else {}
                    labeled_transcript = s04_labeled_transcript.run(transcript_data, predicted_map, guest_name)
                elif step_number == 5:
                    from app.pipeline.steps import s05_energy_map
                    energy_data = s05_energy_map.run(audio_path, job_id)
                elif step_number == 6:
                    from app.pipeline.steps import s06_video_analysis
                    visual_events = s06_video_analysis.run(video_path, job_id)
                elif step_number == 7:
                    from app.pipeline.steps import s07_context_build
                    context = s07_context_build.run(guest_name, channel_id, video_title)
                elif step_number == 8:
                    from app.pipeline.steps import s07b_humor_map
                    supabase = get_client()
                    channel_res = supabase.table("channels").select("channel_dna").eq("id", channel_id).execute()
                    if channel_res.data and len(channel_res.data) > 0:
                        channel_dna = channel_res.data[0].get("channel_dna") or {}
                    humor_moments = s07b_humor_map.run(labeled_transcript, channel_dna, job_id)
                elif step_number == 9:
                    from app.pipeline.steps import s07c_signal_fusion
                    fused_timeline = s07c_signal_fusion.run(labeled_transcript, energy_data, visual_events, humor_moments, job_id)
                elif step_number == 10:
                    from app.pipeline.steps import s08_clip_finder
                    
                    # Ensure channel exists
                    supabase = get_client()
                    channel_resp = supabase.table("channels").select("*").eq("id", channel_id).single().execute()
                    channel = channel_resp.data if channel_resp.data else {}
                    
                    video_duration_s = energy_data.get("duration_s", energy_data.get("duration", 0.0)) if energy_data else 0.0
                    
                    # S08 - Clip Finder
                    s08_result = s08_clip_finder.run(
                        fused_timeline,
                        labeled_transcript,
                        context,
                        channel.get("channel_dna", channel_dna) if channel else channel_dna,
                        video_duration_s,
                        job_id
                    )

                    # Extract clips from result dict
                    if isinstance(s08_result, dict):
                        # s08_clip_finder returns keys "selected" and "evaluated"
                        selected_clips = s08_result.get("selected_clips", s08_result.get("selected", []))
                        evaluated_clips = s08_result.get("evaluated_clips", s08_result.get("evaluated", []))
                    elif isinstance(s08_result, list):
                        selected_clips = s08_result
                        evaluated_clips = s08_result
                    else:
                        selected_clips = []
                        evaluated_clips = []

                    print(f"[Orchestrator] S08 returned {len(selected_clips)} selected clips")
                    
                elif step_number == 11:
                    from app.pipeline.steps import s09_quality_gate
                    # S09 - Quality Gate (pass selected_clips)
                    quality_results = s09_quality_gate.run(selected_clips, evaluated_clips, labeled_transcript, job_id)
                elif step_number == 12:
                    from app.pipeline.steps import s09b_clip_strategy
                    strategy_results = s09b_clip_strategy.run(quality_results, evaluated_clips, channel_dna, job_id)
                elif step_number == 13:
                    from app.pipeline.steps import s10_precision_cut
                    cut_results = s10_precision_cut.run(strategy_results, transcript_data, video_path, job_id)
                elif step_number == 14:
                    from app.pipeline.steps import s11_export
                    exported_clips = s11_export.run(cut_results, job_id)
                    
                duration_ms = int((time.time() - step_start_time) * 1000)
                log_step(job_id, step_number, step_name, StepStatus.COMPLETED.value, duration_ms=duration_ms)
                
            except Exception as e:
                error_msg = str(e)
                print(f"[Orchestrator] Error in step {step_name}: {error_msg}")
                traceback.print_exc()
                
                duration_ms = int((time.time() - step_start_time) * 1000)
                log_step(
                    job_id=job_id,
                    step_number=step_number,
                    step_name=step_name,
                    status=StepStatus.FAILED.value,
                    duration_ms=duration_ms,
                    error_message=error_msg
                )
                
                update_job(
                    job_id=job_id,
                    status=JobStatus.FAILED.value,
                    error_message=f"Step {step_name} failed: {error_msg}"
                )
                return  # Return early on any step failure
                
        # After all steps complete
        completed_at = datetime.now(timezone.utc).isoformat()
        clip_count = len(exported_clips) if 'exported_clips' in locals() and exported_clips else 0
        update_job(
            job_id=job_id,
            status=JobStatus.COMPLETED.value,
            progress_pct=100,
            completed_at=completed_at,
            current_step="finished",
            current_step_number=len(steps),
            clip_count=clip_count
        )
        print(f"[Orchestrator] Job {job_id} pipeline completed successfully.")
        
    except Exception as e:
        error_msg = str(e)
        print(f"[Orchestrator] Pipeline execution failed unexpectedly: {error_msg}")
        traceback.print_exc()
        update_job(
            job_id=job_id,
            status=JobStatus.FAILED.value,
            error_message=f"Pipeline critical failure: {error_msg}"
        )
    finally:
        try:
            supabase = get_client()
            job_res = supabase.table("jobs").select("status").eq("id", job_id).single().execute()
            final_status = job_res.data.get("status") if job_res.data else None
        except Exception:
            final_status = None
            
        if final_status not in ("awaiting_speaker_confirm",):
            for path in [audio_path, video_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                        print(f"[Orchestrator] Cleaned up {path}")
                    except Exception as e:
                        print(f"[Orchestrator] Error cleaning up {path}: {e}")

def resume_pipeline_from_s04(job_id: str, confirmed_speaker_map: dict) -> None:
    """
    Resumes pipeline from step 4 after speakers are confirmed.
    Fetches transcript data from Supabase.
    """
    audio_path = None
    video_path = None
    
    try:
        supabase = get_client()
        
        # 1. Fetch job to get video_path, title, guest_name, channel_id
        job_res = supabase.table("jobs").select("*").eq("id", job_id).single().execute()
        if not job_res.data:
            print(f"[Orchestrator] Job {job_id} not found")
            return
            
        job = job_res.data
        video_path = job.get("video_path")
        video_title = job.get("title", "")
        guest_name = job.get("guest_name")
        channel_id = job.get("channel_id", "speedy_cast")
        
        # Set audio path assuming standard naming
        if video_path:
            import os
            base, ext = os.path.splitext(video_path)
            audio_path = f"{base}.m4a"
            
        # 2. Fetch transcript data
        trans_res = supabase.table("transcripts").select("*").eq("job_id", job_id).single().execute()
        if not trans_res.data:
            print(f"[Orchestrator] Transcript for job {job_id} not found")
            return
            
        transcript_row = trans_res.data
        transcript_data = {
            "raw_response": transcript_row.get("raw_response", {}),
            "words": transcript_row.get("word_timestamps", [])
        }
        
        # 3. Resume the pipeline from step 4
        update_job(
            job_id=job_id,
            status=JobStatus.PROCESSING.value,
            current_step_number=4,
            current_step="s04_labeled_transcript"
        )
        
        steps = [
            (4, "s04_labeled_transcript", 36),
            (5, "s05_energy_map", 44),
            (6, "s06_video_analysis", 52),
            (7, "s07_context_build", 58),
            (8, "s07b_humor_map", 64),
            (9, "s07c_signal_fusion", 70),
            (10, "s08_clip_finder", 80),
            (11, "s09_quality_gate", 88),
            (12, "s09b_clip_strategy", 92),
            (13, "s10_precision_cut", 96),
            (14, "s11_export", 100)
        ]
        
        # State variables
        labeled_transcript = None
        energy_data = None
        visual_events = None
        context = None
        channel_dna = {}
        humor_moments = None
        fused_timeline = None
        exported_clips = []
        
        for step_number, step_name, progress_pct in steps:
            step_start_time = time.time()
            log_step(job_id, step_number, step_name, StepStatus.STARTED.value)
            
            update_job(
                job_id=job_id,
                current_step=step_name,
                current_step_number=step_number,
                progress_pct=progress_pct
            )
            
            try:
                if step_number == 4:
                    from app.pipeline.steps import s04_labeled_transcript
                    labeled_transcript = s04_labeled_transcript.run(transcript_data, confirmed_speaker_map, guest_name)
                elif step_number == 5:
                    from app.pipeline.steps import s05_energy_map
                    energy_data = s05_energy_map.run(audio_path, job_id)
                elif step_number == 6:
                    from app.pipeline.steps import s06_video_analysis
                    visual_events = s06_video_analysis.run(video_path, job_id)
                elif step_number == 7:
                    from app.pipeline.steps import s07_context_build
                    context = s07_context_build.run(guest_name, channel_id, video_title)
                elif step_number == 8:
                    from app.pipeline.steps import s07b_humor_map
                    channel_res = supabase.table("channels").select("channel_dna").eq("id", channel_id).execute()
                    if channel_res.data and len(channel_res.data) > 0:
                        channel_dna = channel_res.data[0].get("channel_dna") or {}
                    humor_moments = s07b_humor_map.run(labeled_transcript, channel_dna, job_id)
                elif step_number == 9:
                    from app.pipeline.steps import s07c_signal_fusion
                    fused_timeline = s07c_signal_fusion.run(labeled_transcript, energy_data, visual_events, humor_moments, job_id)
                elif step_number == 10:
                    from app.pipeline.steps import s08_clip_finder
                    
                    channel_resp = supabase.table("channels").select("*").eq("id", channel_id).single().execute()
                    channel = channel_resp.data if channel_resp.data else {}
                    
                    video_duration_s = energy_data.get("duration_s", energy_data.get("duration", 0.0)) if energy_data else 0.0
                    
                    s08_result = s08_clip_finder.run(
                        fused_timeline,
                        labeled_transcript,
                        context,
                        channel.get("channel_dna", channel_dna) if channel else channel_dna,
                        video_duration_s,
                        job_id
                    )

                    if isinstance(s08_result, dict):
                        selected_clips = s08_result.get("selected_clips", s08_result.get("selected", []))
                        evaluated_clips = s08_result.get("evaluated_clips", s08_result.get("evaluated", []))
                    elif isinstance(s08_result, list):
                        selected_clips = s08_result
                        evaluated_clips = s08_result
                    else:
                        selected_clips = []
                        evaluated_clips = []

                    print(f"[Orchestrator] S08 returned {len(selected_clips)} selected clips")
                    
                elif step_number == 11:
                    from app.pipeline.steps import s09_quality_gate
                    quality_results = s09_quality_gate.run(selected_clips, evaluated_clips, labeled_transcript, job_id)
                elif step_number == 12:
                    from app.pipeline.steps import s09b_clip_strategy
                    strategy_results = s09b_clip_strategy.run(quality_results, evaluated_clips, channel_dna, job_id)
                elif step_number == 13:
                    from app.pipeline.steps import s10_precision_cut
                    cut_results = s10_precision_cut.run(strategy_results, transcript_data, video_path, job_id)
                elif step_number == 14:
                    from app.pipeline.steps import s11_export
                    exported_clips = s11_export.run(cut_results, job_id)
                    
                duration_ms = int((time.time() - step_start_time) * 1000)
                log_step(job_id, step_number, step_name, StepStatus.COMPLETED.value, duration_ms=duration_ms)
                
            except Exception as e:
                error_msg = str(e)
                print(f"[Orchestrator] Error in step {step_name}: {error_msg}")
                traceback.print_exc()
                
                duration_ms = int((time.time() - step_start_time) * 1000)
                log_step(
                    job_id=job_id,
                    step_number=step_number,
                    step_name=step_name,
                    status=StepStatus.FAILED.value,
                    duration_ms=duration_ms,
                    error_message=error_msg
                )
                
                update_job(
                    job_id=job_id,
                    status=JobStatus.FAILED.value,
                    error_message=f"Step {step_name} failed: {error_msg}"
                )
                return
                
        # After all steps complete
        completed_at = datetime.now(timezone.utc).isoformat()
        clip_count = len(exported_clips) if exported_clips else 0
        update_job(
            job_id=job_id,
            status=JobStatus.COMPLETED.value,
            progress_pct=100,
            completed_at=completed_at,
            current_step="finished",
            current_step_number=14,
            clip_count=clip_count
        )
        print(f"[Orchestrator] Job {job_id} resumed pipeline completed successfully.")
        
    except Exception as e:
        error_msg = str(e)
        print(f"[Orchestrator] Resumed pipeline execution failed unexpectedly: {error_msg}")
        traceback.print_exc()
        update_job(
            job_id=job_id,
            status=JobStatus.FAILED.value,
            error_message=f"Resumed pipeline critical failure: {error_msg}"
        )
    finally:
        for path in [audio_path, video_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"[Orchestrator] Cleaned up {path}")
                except Exception as e:
                    print(f"[Orchestrator] Error cleaning up {path}: {e}")
