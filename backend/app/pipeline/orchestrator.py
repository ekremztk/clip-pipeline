from datetime import datetime, timezone
import time
import os
import traceback

from app.config import settings
from app.services.supabase_client import get_client
from app.models.enums import JobStatus, StepStatus
from app.services import storage
from app.director.events import director_events


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
             duration_ms: int | None = None, error_message: str | None = None,
             token_usage: dict | None = None) -> None:
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
        error_message=error_message,
        token_usage=token_usage,
    )


def run_pipeline(job_id: str, video_path: str, video_title: str,
                 guest_name: str | None, channel_id: str, user_id: str | None = None,
                 clip_duration_min: int | None = None,
                 clip_duration_max: int | None = None) -> None:
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

        # Director hook: pipeline started
        director_events.emit_sync(
            module="module_1",
            event="pipeline_started",
            payload={"job_id": job_id, "channel_id": channel_id,
                     "guest_name_provided": bool(guest_name)},
            channel_id=channel_id,
        )

        # Fetch job + channel metadata (reframe + caption settings)
        job_row = get_client().table("jobs").select("reframe_content_type, caption_template").eq("id", job_id).execute()
        reframe_content_type = "podcast"
        caption_template = "clean"
        if job_row.data:
            reframe_content_type = job_row.data[0].get("reframe_content_type") or "podcast"
            caption_template = job_row.data[0].get("caption_template") or "clean"

        # Fetch channel_dna early — needed by S02 (keyterms) and S05/S06
        try:
            channel_res = get_client().table("channels").select("channel_dna").eq("id", channel_id).execute()
            if channel_res.data and len(channel_res.data) > 0:
                channel_dna = channel_res.data[0].get("channel_dna") or {}
        except Exception as e:
            print(f"[Orchestrator] Warning: Could not fetch channel_dna early: {e}")

        steps = [
            (1,  "s01_audio_extract",      5),
            (2,  "s02_transcribe",         15),
            (3,  "s03_speaker_id",         22),
            (4,  "s04_labeled_transcript",  30),
            (5,  "s05_unified_discovery",   65),
            (6,  "s06_batch_evaluation",    85),
            (7,  "s07_precision_cut",       92),
            (8,  "s08_export",              95),
            (9,  "s09_reframe",             98),
            (10, "s10_captions",           100),
        ]

        # State variables to pass between steps
        transcript_data = None
        speaker_data = None
        labeled_transcript = None
        channel_dna = {}
        candidates = []
        evaluated_clips = []
        cut_results = []
        exported_clips = []
        reframed_clips = []
        captioned_clips = []
        pass_count = 0

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
                    transcript_data = s02_transcribe.run(
                        audio_path, job_id,
                        channel_dna=channel_dna,
                        video_title=video_title,
                        guest_name=guest_name,
                    )
                elif step_number == 3:
                    from app.pipeline.steps import s03_speaker_id
                    speaker_data = s03_speaker_id.run(transcript_data, job_id, video_title)

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
                        "speaker_confirmed": True
                    }).execute()

                    print(f"[Orchestrator] S03 completed, continuing to S04 automatically")
                elif step_number == 4:
                    from app.pipeline.steps import s04_labeled_transcript
                    predicted_map = speaker_data.get("predicted_map", {}) if speaker_data else {}
                    labeled_transcript = s04_labeled_transcript.run(transcript_data, predicted_map, guest_name)
                elif step_number == 5:
                    from app.pipeline.steps import s05_unified_discovery
                    from app.services.gemini_client import reset_token_accumulator, get_accumulated_token_usage
                    # channel_dna already fetched at pipeline start
                    # Get video duration from transcript_data (Deepgram provides this)
                    video_duration_s = transcript_data.get("duration", 0.0) if transcript_data else 0.0
                    # guest_name is already available as a function parameter
                    reset_token_accumulator()
                    candidates = s05_unified_discovery.run(
                        video_path=video_path,
                        labeled_transcript=labeled_transcript,
                        channel_dna=channel_dna,
                        guest_name=guest_name,
                        channel_id=channel_id,
                        video_duration_s=video_duration_s,
                        job_id=job_id,
                        audio_path=audio_path,
                        clip_duration_min=clip_duration_min,
                        clip_duration_max=clip_duration_max,
                    )
                    s05_token_usage = get_accumulated_token_usage()
                    print(f"[Orchestrator] S05 returned {len(candidates)} candidates")
                    duration_ms_s05 = int((time.time() - step_start_time) * 1000)
                    log_step(job_id, step_number, step_name, StepStatus.COMPLETED.value,
                             duration_ms=duration_ms_s05, token_usage=s05_token_usage)
                    director_events.emit_sync(
                        module="module_1", event="s05_discovery_completed",
                        payload={"job_id": job_id, "candidate_count": len(candidates),
                                 "duration_ms": duration_ms_s05,
                                 "channel_dna_present": bool(channel_dna),
                                 "guest_name_provided": bool(guest_name)},
                        channel_id=channel_id,
                    )
                    continue  # log_step already called above

                elif step_number == 6:
                    from app.pipeline.steps import s06_batch_evaluation
                    if not candidates:
                        print("[Orchestrator] No candidates from S05. Skipping evaluation.")
                    else:
                        evaluated_clips = s06_batch_evaluation.run(
                            candidates=candidates,
                            labeled_transcript=labeled_transcript,
                            transcript_data=transcript_data,
                            channel_dna=channel_dna,
                            channel_id=channel_id,
                            job_id=job_id,
                            video_path=video_path,
                            clip_duration_min=clip_duration_min,
                            clip_duration_max=clip_duration_max,
                        )
                    print(f"[Orchestrator] S06 returned {len(evaluated_clips)} approved clips (fails already dropped)")
                    duration_ms_s06 = int((time.time() - step_start_time) * 1000)
                    log_step(job_id, step_number, step_name, StepStatus.COMPLETED.value,
                             duration_ms=duration_ms_s06)
                    pass_count = len(evaluated_clips)
                    avg_score = round(
                        sum(float(c.get("score", 0) or 0) for c in evaluated_clips) / max(len(evaluated_clips), 1), 2
                    )
                    director_events.emit_sync(
                        module="module_1", event="s06_evaluation_completed",
                        payload={"job_id": job_id, "pass_count": pass_count,
                                 "avg_score": avg_score,
                                 "duration_ms": duration_ms_s06},
                        channel_id=channel_id,
                    )
                    continue  # log_step already called above

                elif step_number == 7:
                    from app.pipeline.steps import s07_precision_cut
                    if not evaluated_clips:
                        print("[Orchestrator] No evaluated clips. Skipping precision cut.")
                    else:
                        cut_results = s07_precision_cut.run(
                            evaluated_clips=evaluated_clips,
                            transcript_data=transcript_data,
                            video_path=video_path,
                            job_id=job_id,
                            clip_duration_min=clip_duration_min,
                            clip_duration_max=clip_duration_max,
                        )
                    print(f"[Orchestrator] S07 returned {len(cut_results)} clips with boundaries")
                    duration_ms_s07 = int((time.time() - step_start_time) * 1000)
                    director_events.emit_sync(
                        module="module_1", event="s07_precision_cut_completed",
                        payload={"job_id": job_id, "clips_cut": len(cut_results),
                                 "duration_ms": duration_ms_s07},
                        channel_id=channel_id,
                    )

                elif step_number == 8:
                    from app.pipeline.steps import s08_export
                    if not cut_results:
                        print("[Orchestrator] No cut results. Skipping export.")
                    else:
                        exported_clips = s08_export.run(
                            cut_results=cut_results,
                            job_id=job_id,
                            channel_id=channel_id,
                            video_path=video_path,
                            video_title=video_title,
                            user_id=user_id,
                            transcript_data=transcript_data,
                        )
                    print(f"[Orchestrator] S08 exported {len(exported_clips)} clips")
                    duration_ms_s08 = int((time.time() - step_start_time) * 1000)
                    director_events.emit_sync(
                        module="module_1", event="s08_export_completed",
                        payload={"job_id": job_id, "exported_count": len(exported_clips),
                                 "duration_ms": duration_ms_s08},
                        channel_id=channel_id,
                    )

                elif step_number == 9:
                    from app.pipeline.steps import s09_reframe
                    if not exported_clips:
                        print("[Orchestrator] No exported clips. Skipping reframe.")
                    else:
                        reframed_clips = s09_reframe.run(
                            exported_clips=exported_clips,
                            job_id=job_id,
                            channel_id=channel_id,
                            reframe_content_type=reframe_content_type,
                        )
                    reframed_count = sum(1 for c in reframed_clips if c.get("video_reframed_path"))
                    print(f"[Orchestrator] S09 reframed {reframed_count}/{len(exported_clips)} clips")
                    duration_ms_s09 = int((time.time() - step_start_time) * 1000)
                    director_events.emit_sync(
                        module="module_1", event="s09_reframe_completed",
                        payload={"job_id": job_id, "reframed_count": reframed_count,
                                 "strategy": reframe_content_type,
                                 "duration_ms": duration_ms_s09},
                        channel_id=channel_id,
                    )

                elif step_number == 10:
                    from app.pipeline.steps import s10_captions
                    source_clips = reframed_clips if reframed_clips else exported_clips
                    if not source_clips:
                        print("[Orchestrator] No clips to caption. Skipping S10.")
                    else:
                        captioned_clips = s10_captions.run(
                            reframed_clips=source_clips,
                            job_id=job_id,
                            channel_id=channel_id,
                            caption_template=caption_template,
                        )
                    captioned_count = sum(1 for c in captioned_clips if c.get("video_captioned_path"))
                    print(f"[Orchestrator] S10 captioned {captioned_count}/{len(source_clips)} clips")
                    duration_ms_s10 = int((time.time() - step_start_time) * 1000)
                    director_events.emit_sync(
                        module="module_1", event="s10_captions_completed",
                        payload={"job_id": job_id, "captioned_count": captioned_count,
                                 "template": caption_template,
                                 "duration_ms": duration_ms_s10},
                        channel_id=channel_id,
                    )

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
                try:
                    director_events.emit_sync(
                        module="module_1", event="pipeline_error",
                        payload={"job_id": job_id, "step": step_name, "error": error_msg},
                        channel_id=channel_id,
                    )
                except Exception:
                    pass
                try:
                    from app.director.notifier import notify_pipeline_failed
                    notify_pipeline_failed(job_id, step_name, error_msg, channel_id)
                except Exception:
                    pass
                director_events.emit_sync(
                    module="module_1", event="pipeline_failed",
                    payload={"job_id": job_id, "failed_at_step": step_name,
                             "error_message": error_msg},
                    channel_id=channel_id,
                )
                return  # Return early on any step failure

        # After all steps complete
        completed_at = datetime.now(timezone.utc).isoformat()
        clip_count = len(exported_clips) if exported_clips else 0
        update_job(
            job_id=job_id,
            status=JobStatus.COMPLETED.value,
            progress_pct=100,
            completed_at=completed_at,
            current_step="finished",
            current_step_number=10,
            clip_count=clip_count
        )
        director_events.emit_sync(
            module="module_1", event="pipeline_completed",
            payload={"job_id": job_id, "clip_count": clip_count,
                     "pass_clips": pass_count if evaluated_clips else 0},
            channel_id=channel_id,
        )
        print(f"[Orchestrator] Job {job_id} pipeline completed successfully.")
        # Cross-module signal: M1 clips ready for M2 editor
        try:
            from app.services.supabase_client import get_client as _get_client
            _get_client().table("director_cross_module_signals").insert({
                "signal_type": "clips_ready_for_editor",
                "source_module": "module_1",
                "target_module": "module_2",
                "payload": {"job_id": job_id, "pass_clips": pass_count, "clip_count": clip_count},
                "channel_id": channel_id,
            }).execute()
        except Exception as _cme:
            print(f"[Orchestrator] Cross-module signal error (non-critical): {_cme}")
        # Run proactive checks after every pipeline completion (non-blocking)
        try:
            from app.director.proactive import run_proactive_checks
            run_proactive_checks(job_id=job_id)
        except Exception as _pe:
            print(f"[Orchestrator] Proactive check error (non-critical): {_pe}")

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
        for path in [audio_path, video_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"[Orchestrator] Cleaned up {path}")
                except Exception as e:
                    print(f"[Orchestrator] Error cleaning up {path}: {e}")

