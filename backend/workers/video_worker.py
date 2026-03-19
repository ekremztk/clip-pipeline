import os
import time
import traceback
from datetime import datetime, timezone

from app.pipeline.orchestrator import run_pipeline, update_job, log_step
from app.services.supabase_client import get_client
from app.models.enums import JobStatus, StepStatus


def start_pipeline(job_id: str, video_path: str, video_title: str,
                   guest_name: str | None, channel_id: str) -> None:
    """
    Simply calls run_pipeline with all params
    Wraps in try/except, prints [Worker] prefixed logs
    """
    try:
        print(f"[Worker] Starting pipeline for job {job_id}")
        run_pipeline(job_id, video_path, video_title, guest_name, channel_id)
        print(f"[Worker] Pipeline completed for job {job_id}")
    except Exception as e:
        print(f"[Worker] Error starting pipeline for job {job_id}: {e}")
        traceback.print_exc()


def resume_pipeline_from_s04(job_id: str, confirmed_speaker_map: dict) -> None:
    """
    Resumes pipeline from s04 after speaker confirmation.
    """
    audio_path = None
    try:
        print(f"[Worker] Resuming pipeline from s04 for job {job_id}")
        supabase = get_client()

        # Fetch transcript from transcripts table
        transcript_res = supabase.table("transcripts").select("*").eq("job_id", job_id).execute()
        if not transcript_res.data:
            raise Exception("Transcript not found")
        transcript_record = transcript_res.data[0]
        
        # Reconstruct transcript_data from stored columns
        raw_response = transcript_record.get("raw_response", {})
        if isinstance(raw_response, str):
            import json
            try:
                raw_response = json.loads(raw_response)
            except json.JSONDecodeError:
                raw_response = {}
                
        words = transcript_record.get("word_timestamps", [])
        if isinstance(words, str):
            import json
            try:
                words = json.loads(words)
            except json.JSONDecodeError:
                words = []
                
        utterances = raw_response.get("results", {}).get("utterances", []) if isinstance(raw_response, dict) else []
        
        transcript_data = {
            "raw_response": raw_response,
            "words": words,
            "utterances": utterances
        }

        # Add duration from raw_response metadata
        duration = raw_response.get("metadata", {}).get("duration", 0) if isinstance(raw_response, dict) else 0
        transcript_data["duration"] = duration

        # In case we need previous step results that might not be in db but we need to re-run or fetch
        labeled_transcript = transcript_record.get("labeled_transcript")

        # Fetch job from jobs table
        job_res = supabase.table("jobs").select("*").eq("id", job_id).execute()
        if not job_res.data:
            raise Exception("Job not found")
        job_record = job_res.data[0]

        video_path = job_record.get("video_path")
        
        # Fallback for old jobs where video_path wasn't saved to DB
        if not video_path:
            import glob
            from app.services.storage import UPLOAD_DIR
            possible_files = glob.glob(os.path.join(UPLOAD_DIR, f"{job_id}_*"))
            if possible_files:
                video_path = possible_files[0]
                print(f"[Worker] Found video_path via fallback: {video_path}")
            else:
                raise Exception(f"Video file for job {job_id} not found in DB or on disk")
                
        video_title = job_record.get("title", "")
        guest_name = job_record.get("guest_name")
        channel_id = job_record.get("channel_id")
        if not channel_id:
            print(f"[Worker] WARNING: job {job_id} has no channel_id in database")
            channel_id = "unknown"

        # Set job to processing
        update_job(job_id=job_id, status=JobStatus.PROCESSING.value)

        steps = [
            (4, "s04_labeled_transcript", 30),
            (5, "s05_unified_discovery", 65),
            (6, "s06_batch_evaluation", 85),
            (7, "s07_precision_cut", 92),
            (8, "s08_export", 100)
        ]

        channel_dna = {}
        candidates = []
        evaluated_clips = []
        cut_results = []
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
                    from app.pipeline.steps import s05_unified_discovery
                    channel_res = supabase.table("channels").select("channel_dna").eq("id", channel_id).execute()
                    if channel_res.data and len(channel_res.data) > 0:
                        channel_dna = channel_res.data[0].get("channel_dna") or {}
                    video_duration_s = transcript_data.get("duration", 0.0) if transcript_data else 0.0
                    candidates = s05_unified_discovery.run(
                        video_path=video_path,
                        labeled_transcript=labeled_transcript,
                        channel_dna=channel_dna,
                        guest_name=guest_name,
                        channel_id=channel_id,
                        video_duration_s=video_duration_s,
                        job_id=job_id
                    )
                    print(f"[Worker] S05 returned {len(candidates)} candidates")

                elif step_number == 6:
                    from app.pipeline.steps import s06_batch_evaluation
                    if not candidates:
                        print("[Worker] No candidates from S05. Skipping evaluation.")
                    else:
                        evaluated_clips = s06_batch_evaluation.run(
                            candidates=candidates,
                            labeled_transcript=labeled_transcript,
                            transcript_data=transcript_data,
                            channel_dna=channel_dna,
                            channel_id=channel_id,
                            job_id=job_id
                        )
                    print(f"[Worker] S06 returned {len(evaluated_clips)} evaluated clips")

                elif step_number == 7:
                    from app.pipeline.steps import s07_precision_cut
                    if not evaluated_clips:
                        print("[Worker] No evaluated clips. Skipping precision cut.")
                    else:
                        cut_results = s07_precision_cut.run(
                            evaluated_clips=evaluated_clips,
                            transcript_data=transcript_data,
                            video_path=video_path,
                            job_id=job_id
                        )
                    print(f"[Worker] S07 returned {len(cut_results)} clips with boundaries")

                elif step_number == 8:
                    from app.pipeline.steps import s08_export
                    if not cut_results:
                        print("[Worker] No cut results. Skipping export.")
                    else:
                        exported_clips = s08_export.run(
                            cut_results=cut_results,
                            job_id=job_id,
                            channel_id=channel_id,
                            video_path=video_path,
                            video_title=video_title
                        )
                    print(f"[Worker] S08 exported {len(exported_clips)} clips")

                duration_ms = int((time.time() - step_start_time) * 1000)
                log_step(job_id, step_number, step_name, StepStatus.COMPLETED.value, duration_ms=duration_ms)

            except Exception as e:
                error_msg = str(e)
                print(f"[Worker] Error in step {step_name}: {error_msg}")
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
            current_step_number=len(steps),
            clip_count=clip_count
        )
        print(f"[Worker] Job {job_id} resume pipeline completed successfully.")

    except Exception as e:
        error_msg = str(e)
        print(f"[Worker] Resume pipeline execution failed unexpectedly: {error_msg}")
        traceback.print_exc()
        update_job(
            job_id=job_id,
            status=JobStatus.FAILED.value,
            error_message=f"Pipeline critical failure: {error_msg}"
        )
    finally:
        for path in [audio_path, video_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"[Worker] Cleaned up {path}")
                except Exception as e:
                    print(f"[Worker] Error cleaning up {path}: {e}")
