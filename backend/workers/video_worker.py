import os
import time
import traceback
from datetime import datetime, timezone

from app.pipeline.orchestrator import run_pipeline, update_job, log_step
from app.services.supabase_client import get_client
from app.models.enums import JobStatus, StepStatus


def start_pipeline(job_id: str, video_path: str, video_title: str,
                   guest_name: str = None, channel_id: str = "speedy_cast") -> None:
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
        transcript_data = transcript_record.get("transcript_data")

        # In case we need previous step results that might not be in db but we need to re-run or fetch
        labeled_transcript = transcript_record.get("labeled_transcript")
        energy_map = transcript_record.get("energy_map")
        visual_events = transcript_record.get("visual_events")
        humor_moments = transcript_record.get("humor_moments")

        # Fetch job from jobs table
        job_res = supabase.table("jobs").select("*").eq("id", job_id).execute()
        if not job_res.data:
            raise Exception("Job not found")
        job_record = job_res.data[0]

        video_path = job_record.get("video_path")
        video_title = job_record.get("title", "")
        guest_name = job_record.get("guest_name")
        channel_id = job_record.get("channel_id", "speedy_cast")

        # Set job to processing
        update_job(job_id=job_id, status=JobStatus.PROCESSING.value)

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

        channel_dna = {}
        context = None
        fused_timeline = None

        # Reconstruct audio_path if we need it for s05 (it might not exist if deleted, need to extract again or gracefully skip)
        # However, the instruction says: "s05_energy_map.run(audio_path, job_id) — note: audio may be gone, handle gracefully"
        audio_path = video_path.replace(".mp4", ".m4a") if video_path else "temp_audio.m4a"

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
                    if not os.path.exists(audio_path):
                        print(f"[Worker] Audio file missing, re-extracting...")
                        from app.pipeline.steps import s01_audio_extract
                        audio_path = s01_audio_extract.run(video_path, job_id)
                    energy_map = s05_energy_map.run(audio_path, job_id)
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
                    fused_timeline = s07c_signal_fusion.run(labeled_transcript, energy_map, visual_events, humor_moments, job_id)
                elif step_number == 10:
                    from app.pipeline.steps import s08_clip_finder
                    video_duration_s = energy_map.get("duration", 0.0) if energy_map else 0.0
                    s08_result = s08_clip_finder.run(
                        fused_timeline,
                        labeled_transcript,
                        context,
                        channel_dna,
                        video_duration_s,
                        job_id
                    )
                    selected_clips = s08_result.get("selected_clips", [])
                    evaluated_clips = s08_result.get("evaluated_clips", [])
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
