from datetime import datetime, timezone
import time
import os
import json
import traceback

from app.config import settings
from app.services.supabase_client import get_client
from app.models.enums import JobStatus, StepStatus
from app.services import storage
from app.director.events import director_events

PIPELINE_DEBUG = os.getenv("PIPELINE_DEBUG", "0") == "1"
SCENE_FILTER_DEBUG = os.getenv("SCENE_FILTER_DEBUG", "0") == "1"
_DEBUG_DIR = None

def _debug_dump(job_id: str, step: str, data: object) -> None:
    if not PIPELINE_DEBUG:
        return
    debug_dir = f"/tmp/pipeline_debug_{job_id}"
    os.makedirs(debug_dir, exist_ok=True)
    path = f"{debug_dir}/{step}.json"
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"[DEBUG] {step} → {path}")
    except Exception as e:
        print(f"[DEBUG] Could not write {step}: {e}")


def _fmt_ts(sec: float) -> str:
    m = int(sec // 60)
    s = sec % 60
    return f"{m:02d}:{s:05.2f}"


def _build_scene_filter_report(
    job_id: str,
    video_title: str,
    target_guest: str | None,
    speaker_data: dict,
    scene_result: dict,
    transcript_data: dict,
    labeled_transcript_full: str,
    labeled_transcript_filtered: str,
) -> str:
    """Render a human-readable scene-filter audit report."""
    lines: list[str] = []
    lines.append(f"=== JOB {job_id} ===")
    lines.append(f"Episode title: {video_title}")
    stats = scene_result.get("stats", {}) or {}
    lines.append(f"Episode length: {_fmt_ts(stats.get('episode_sec', 0.0))}")
    lines.append(f"Target guest: {target_guest or '(none)'}")
    lines.append(f"Filter active: {scene_result.get('active')}")
    lines.append(f"Reason: {scene_result.get('reason')}")
    lines.append("")

    lines.append("=== SPEAKER MAP (from S03) ===")
    # Collect all speaker IDs matched to target (multi-cluster support)
    target_name = (target_guest or "").strip().lower()
    for spk_id, info in (speaker_data.get("predicted_map", {}) or {}).items():
        role = (info or {}).get("role", "?")
        name = (info or {}).get("name") or "(unmatched)"
        is_target = ""
        if name and name.strip().lower() == target_name:
            is_target = "  ← TARGET"
        elif str(spk_id) == str(scene_result.get("target_speaker_id")):
            is_target = "  ← TARGET (primary)"
        lines.append(f"  speaker {spk_id}: {role} / {name}{is_target}")
    lines.append("")

    lines.append("=== DENSITY MAP (30s windows, 15s stride) ===")
    for w in scene_result.get("windows", []) or []:
        lines.append(
            f"  {_fmt_ts(w['start'])}-{_fmt_ts(w['end'])}  "
            f"target={w['target_pct']*100:5.1f}%  "
            f"utts={w['utt_count']:>2}  "
            f"spk={w['speakers']}  "
            f"→ {w['decision']}"
        )
    lines.append("")

    lines.append("=== KEPT SCENES (merged, padded, utterance-snapped) ===")
    for i, (s, e) in enumerate(scene_result.get("kept_ranges", []) or []):
        lines.append(f"  Scene {i + 1}: {_fmt_ts(s)} → {_fmt_ts(e)}  ({_fmt_ts(e - s)})")
    lines.append(f"  Total kept: {_fmt_ts(stats.get('kept_sec', 0.0))} / "
                 f"{_fmt_ts(stats.get('episode_sec', 0.0))} "
                 f"({stats.get('coverage_pct', 0.0) * 100:.1f}%)")
    lines.append("")

    lines.append("=== RAW UTTERANCES (full transcript, pre-filter) ===")
    lines.append(labeled_transcript_full or "(empty)")
    lines.append("")

    lines.append("=== FILTERED UTTERANCES (what S05 sees) ===")
    lines.append(labeled_transcript_filtered or "(filter disabled — S05 sees full transcript)")

    return "\n".join(lines)


def _upload_scene_filter_report(job_id: str, report: str) -> str | None:
    """Upload the scene-filter debug report as text to R2. Returns public URL."""
    try:
        from app.services.r2_client import get_r2_client
        s3 = get_r2_client()
        if not settings.R2_BUCKET_NAME:
            return None
        key = f"debug/scene_filter/{job_id}.txt"
        s3.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=report.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        base = (settings.R2_PUBLIC_URL or "").rstrip("/")
        return f"{base}/{key}" if base else key
    except Exception as e:
        print(f"[SceneFilter] R2 upload error: {e}")
        return None


def _cleanup_pipeline_r2(
    job_id: str,
    exported_clips: list,
    reframed_clips: list,
    captioned_clips: list,
) -> None:
    """
    After S10 finishes, delete transient R2 objects that the UI doesn't need.
    Only captions/ (S10 final) and voice-library/ are permanent.

    - source_videos/{job_id}/* → Modal input, always deletable
    - {job_id}/* (S08 landscape) → deletable ONLY if S10 produced a captioned URL
      for every clip; if some S10 failed, keep S08 as fallback.
    - upscale/{job_id}/* → S08.5 landscape intermediates, deletable if S10
      produced a captioned URL for every clip
    - reframe/*, gaming-reframe/* → deletable if corresponding S10 succeeded
    """
    from app.services.r2_client import delete_prefix, delete_url

    # source_videos is always safe to remove after pipeline finishes
    try:
        n = delete_prefix(f"source_videos/{job_id}/")
        print(f"[Cleanup] Removed {n} source_videos objects for {job_id}")
    except Exception as e:
        print(f"[Cleanup] source_videos/{job_id}/ delete error: {e}")

    # Build a map of clip_id → captioned URL to know which reframe/landscape to keep
    cap_by_clip = {}
    for c in captioned_clips or []:
        cid = c.get("id") or c.get("clip_id")
        cap_url = c.get("video_captioned_path")
        if cid and cap_url:
            cap_by_clip[cid] = cap_url

    all_have_captions = (
        exported_clips
        and captioned_clips
        and len(cap_by_clip) == len(exported_clips)
    )

    # If every clip has a caption URL, S08 landscape output is safe to drop
    if all_have_captions:
        try:
            n = delete_prefix(f"{job_id}/")
            print(f"[Cleanup] Removed {n} landscape (S08) objects for {job_id}")
        except Exception as e:
            print(f"[Cleanup] {job_id}/ delete error: {e}")
        try:
            n = delete_prefix(f"upscale/{job_id}/")
            print(f"[Cleanup] Removed {n} upscaled landscape (S08.5) objects for {job_id}")
        except Exception as e:
            print(f"[Cleanup] upscale/{job_id}/ delete error: {e}")

    # Reframe intermediates — delete per-clip where captioned exists
    for c in reframed_clips or []:
        cid = c.get("id") or c.get("clip_id")
        reframe_url = c.get("video_reframed_path")
        if cid in cap_by_clip and reframe_url:
            delete_url(reframe_url)


def _upload_source_video_to_r2(job_id: str, video_path: str) -> str:
    """Upload source video to R2 and return public URL for Modal to download."""
    import uuid
    from app.services.r2_client import get_r2_client
    from app.config import settings as _s

    s3 = get_r2_client()
    key = f"source_videos/{job_id}/{uuid.uuid4().hex}.mp4"
    with open(video_path, "rb") as f:
        s3.put_object(
            Bucket=_s.R2_BUCKET_NAME,
            Key=key,
            Body=f.read(),
            ContentType="video/mp4",
        )
    public_url = _s.R2_PUBLIC_URL.rstrip("/")
    return f"{public_url}/{key}"


def _dispatch_to_modal(
    job_id: str, channel_id: str, user_id, video_title: str,
    video_path: str, cut_results: list, transcript_data: dict | None,
    reframe_content_type: str, caption_template: str,
) -> dict:
    """
    Upload source video to R2, then call Modal GPU function for S08+S09+S10.
    Falls back to local CPU execution if Modal fails.
    """
    import modal as _modal

    print("[Orchestrator] Uploading source video to R2 for Modal...")
    source_video_url = _upload_source_video_to_r2(job_id, video_path)
    print(f"[Orchestrator] Source video URL: {source_video_url[:80]}...")

    try:
        fn = _modal.Function.from_name("gpu-pipeline", "process_clips")
        result = fn.remote(
            job_id=job_id,
            channel_id=channel_id,
            user_id=user_id,
            video_title=video_title,
            source_video_url=source_video_url,
            clips=cut_results,
            transcript_data=transcript_data,
            reframe_content_type=reframe_content_type,
            caption_template=caption_template,
        )
        return result
    except Exception as e:
        print(f"[Orchestrator] Modal dispatch failed: {e}. Falling back to local CPU.")
        return _run_local_fallback(
            job_id=job_id, channel_id=channel_id, user_id=user_id,
            video_title=video_title, video_path=video_path,
            cut_results=cut_results, transcript_data=transcript_data,
            reframe_content_type=reframe_content_type, caption_template=caption_template,
        )


def _run_local_fallback(
    job_id: str, channel_id: str, user_id, video_title: str,
    video_path: str, cut_results: list, transcript_data: dict | None,
    reframe_content_type: str, caption_template: str,
) -> dict:
    """CPU fallback — runs S08+S08.5+S09+S10 locally on Railway if Modal fails."""
    from app.pipeline.steps import s08_export, s08_5_upscale, s09_reframe, s10_captions
    exported_clips = s08_export.run(
        cut_results=cut_results, job_id=job_id, channel_id=channel_id,
        video_path=video_path, video_title=video_title,
        user_id=user_id, transcript_data=transcript_data,
    )
    exported_clips = s08_5_upscale.run(
        exported_clips=exported_clips,
        job_id=job_id,
        channel_id=channel_id,
    )
    reframed_clips = s09_reframe.run(
        exported_clips=exported_clips, job_id=job_id,
        channel_id=channel_id, reframe_content_type=reframe_content_type,
    )
    source = reframed_clips if reframed_clips else exported_clips
    captioned_clips = s10_captions.run(
        reframed_clips=source, job_id=job_id,
        channel_id=channel_id, caption_template=caption_template,
    )
    return {
        "status": "completed",
        "exported_clips": exported_clips,
        "reframed_clips": reframed_clips,
        "captioned_clips": captioned_clips,
    }


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
                 target_guest: str | None, channel_id: str, user_id: str | None = None,
                 clip_duration_min: int | None = None,
                 clip_duration_max: int | None = None,
                 metadata_subject_name: str | None = None) -> None:
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
            payload={
                "job_id": job_id,
                "channel_id": channel_id,
                "target_guest_provided": bool(target_guest),
                "metadata_subject_provided": bool(metadata_subject_name),
            },
            channel_id=channel_id,
        )

        # Fetch job + channel metadata (reframe + caption settings)
        job_row = get_client().table("jobs").select("reframe_content_type, caption_template").eq("id", job_id).execute()
        reframe_content_type = "podcast"
        caption_template = "clean"
        if job_row.data:
            reframe_content_type = job_row.data[0].get("reframe_content_type") or "podcast"
            caption_template = job_row.data[0].get("caption_template") or "clean"

        steps = [
            (1,  "s01_audio_extract",      5),
            (2,  "s02_transcribe",         15),
            (3,  "s03_speaker_id",         22),
            (4,  "s04_labeled_transcript",  30),
            (5,  "s05_unified_discovery",   65),
            (6,  "s06_batch_evaluation",    85),
            (7,  "s07_precision_cut",       92),
            (8,  "s08_s09_s10_gpu",        100),
        ]

        # State variables to pass between steps — channel_dna MUST be declared
        # before the fetch block so the fetch can populate it
        transcript_data = None
        speaker_data = None
        scene_filter_result = None
        labeled_transcript = None
        channel_dna = {}
        candidates = []

        # Fetch channel_dna early — needed by S02 (keyterms) and S05/S06
        try:
            channel_res = get_client().table("channels").select("channel_dna").eq("id", channel_id).execute()
            if channel_res.data and len(channel_res.data) > 0:
                channel_dna = channel_res.data[0].get("channel_dna") or {}
                print(f"[Orchestrator] channel_dna loaded ({len(channel_dna)} keys)")
        except Exception as e:
            print(f"[Orchestrator] Warning: Could not fetch channel_dna early: {e}")
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
                    _debug_dump(job_id, "s01_audio_extract", {"audio_path": audio_path})
                elif step_number == 2:
                    from app.pipeline.steps import s02_transcribe
                    transcript_data = s02_transcribe.run(
                        audio_path, job_id,
                        channel_dna=channel_dna,
                        video_title=video_title,
                        target_guest=target_guest,
                    )
                    _debug_dump(job_id, "s02_transcribe", transcript_data)
                elif step_number == 3:
                    from app.pipeline.steps import s03_speaker_id
                    speaker_data = s03_speaker_id.run(transcript_data, job_id, video_title, audio_path=audio_path)

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

                    _debug_dump(job_id, "s03_speaker_id", speaker_data)

                    # S03.5 — scene filter (deterministic, never raises)
                    try:
                        from app.pipeline.steps import s03_5_scene_filter
                        scene_filter_result = s03_5_scene_filter.run(
                            transcript_data=transcript_data,
                            speaker_data=speaker_data,
                            target_guest=target_guest,
                        )
                        _debug_dump(job_id, "s03_5_scene_filter", scene_filter_result)
                    except Exception as e:
                        print(f"[Orchestrator] S03.5 scene filter error (non-critical): {e}")
                        scene_filter_result = {"active": False, "reason": f"exception: {e}",
                                               "target_speaker_id": None, "kept_ranges": [],
                                               "windows": [], "stats": {}}

                    print(f"[Orchestrator] S03 completed, continuing to S04 automatically")
                elif step_number == 4:
                    from app.pipeline.steps import s04_labeled_transcript
                    predicted_map = speaker_data.get("predicted_map", {}) if speaker_data else {}

                    # Always build the full labeled transcript (needed for debug report)
                    labeled_transcript_full = s04_labeled_transcript.run(
                        transcript_data, predicted_map, target_guest
                    )

                    # If scene filter is active, build a second, filtered version for S05
                    if scene_filter_result and scene_filter_result.get("active"):
                        scene_ranges = scene_filter_result.get("kept_ranges") or []
                        labeled_transcript = s04_labeled_transcript.run(
                            transcript_data, predicted_map, target_guest,
                            scene_ranges=scene_ranges,
                        )
                    else:
                        labeled_transcript = labeled_transcript_full

                    _debug_dump(job_id, "s04_labeled_transcript", {
                        "labeled_transcript": labeled_transcript,
                        "filter_active": bool(scene_filter_result and scene_filter_result.get("active")),
                    })

                    # Emit scene-filter debug report to R2 when SCENE_FILTER_DEBUG=1
                    if SCENE_FILTER_DEBUG and scene_filter_result is not None:
                        try:
                            report = _build_scene_filter_report(
                                job_id=job_id,
                                video_title=video_title,
                                target_guest=target_guest,
                                speaker_data=speaker_data or {},
                                scene_result=scene_filter_result,
                                transcript_data=transcript_data or {},
                                labeled_transcript_full=labeled_transcript_full,
                                labeled_transcript_filtered=(
                                    labeled_transcript
                                    if scene_filter_result.get("active")
                                    else ""
                                ),
                            )
                            url = _upload_scene_filter_report(job_id, report)
                            if url:
                                print(f"[SceneFilter] debug report → {url}")
                        except Exception as _re:
                            print(f"[SceneFilter] debug report error (non-critical): {_re}")
                elif step_number == 5:
                    from app.pipeline.steps import s05_unified_discovery
                    from app.services.gemini_client import reset_token_accumulator, get_accumulated_token_usage
                    # channel_dna already fetched at pipeline start
                    # Get video duration from transcript_data (Deepgram provides this)
                    video_duration_s = transcript_data.get("duration", 0.0) if transcript_data else 0.0
                    reset_token_accumulator()
                    candidates = s05_unified_discovery.run(
                        video_path=video_path,
                        labeled_transcript=labeled_transcript,
                        channel_dna=channel_dna,
                        channel_id=channel_id,
                        video_duration_s=video_duration_s,
                        job_id=job_id,
                        audio_path=audio_path,
                        clip_duration_min=clip_duration_min,
                        clip_duration_max=clip_duration_max,
                        target_guest=target_guest,
                        scene_filter_active=bool(
                            scene_filter_result
                            and scene_filter_result.get("active")
                        ),
                        scene_ranges=(
                            scene_filter_result.get("kept_ranges")
                            if scene_filter_result
                            else None
                        ),
                    )
                    s05_token_usage = get_accumulated_token_usage()
                    _debug_dump(job_id, "s05_unified_discovery", candidates)
                    try:
                        from app.pipeline.stock_analytics import record_s05_candidates
                        record_s05_candidates(job_id, candidates, source_duration_s=video_duration_s)
                    except Exception as analytics_err:
                        print(f"[StockAnalytics] S05 hook failed: {analytics_err}")
                    print(f"[Orchestrator] S05 returned {len(candidates)} candidates")
                    duration_ms_s05 = int((time.time() - step_start_time) * 1000)
                    log_step(job_id, step_number, step_name, StepStatus.COMPLETED.value,
                             duration_ms=duration_ms_s05, token_usage=s05_token_usage)
                    director_events.emit_sync(
                        module="module_1", event="s05_discovery_completed",
                        payload={"job_id": job_id, "candidate_count": len(candidates),
                                 "duration_ms": duration_ms_s05,
                                 "channel_dna_present": bool(channel_dna),
                                 "target_guest_provided": bool(target_guest)},
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
                            video_title=video_title,
                            metadata_subject_name=metadata_subject_name,
                        )
                    _debug_dump(job_id, "s06_batch_evaluation", evaluated_clips)
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
                            channel_dna=channel_dna,
                        )
                    _debug_dump(job_id, "s07_precision_cut", cut_results)
                    try:
                        from app.pipeline.stock_analytics import record_s07_cuts
                        record_s07_cuts(job_id, cut_results)
                    except Exception as analytics_err:
                        print(f"[StockAnalytics] S07 hook failed: {analytics_err}")
                    print(f"[Orchestrator] S07 returned {len(cut_results)} clips with boundaries")
                    duration_ms_s07 = int((time.time() - step_start_time) * 1000)
                    director_events.emit_sync(
                        module="module_1", event="s07_precision_cut_completed",
                        payload={"job_id": job_id, "clips_cut": len(cut_results),
                                 "duration_ms": duration_ms_s07},
                        channel_id=channel_id,
                    )

                elif step_number == 8:
                    if not cut_results:
                        print("[Orchestrator] No cut results. Skipping GPU steps.")
                    else:
                        print(f"[Orchestrator] Dispatching S08+S09+S10 to Modal GPU ({len(cut_results)} clips)...")
                        result = _dispatch_to_modal(
                            job_id=job_id,
                            channel_id=channel_id,
                            user_id=user_id,
                            video_title=video_title,
                            video_path=video_path,
                            cut_results=cut_results,
                            transcript_data=transcript_data,
                            reframe_content_type=reframe_content_type,
                            caption_template=caption_template,
                        )
                        exported_clips = result.get("exported_clips", [])
                        reframed_clips = result.get("reframed_clips", [])
                        captioned_clips = result.get("captioned_clips", [])
                        duration_gpu = result.get("duration_s", 0)
                        print(f"[Orchestrator] Modal GPU done in {duration_gpu:.1f}s — "
                              f"exported={len(exported_clips)}, reframed={len(reframed_clips)}, captioned={len(captioned_clips)}")
                    director_events.emit_sync(
                        module="module_1", event="s08_s09_s10_gpu_completed",
                        payload={"job_id": job_id,
                                 "exported_count": len(exported_clips),
                                 "reframed_count": sum(1 for c in reframed_clips if c.get("video_reframed_path")),
                                 "captioned_count": sum(1 for c in captioned_clips if c.get("video_captioned_path"))},
                        channel_id=channel_id,
                    )
                    pass  # R2 cleanup moved to finally block

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
                    from app.pipeline.stock_analytics import record_source_failed
                    record_source_failed(job_id, step_name, error_msg)
                except Exception as analytics_err:
                    print(f"[StockAnalytics] Failure hook failed: {analytics_err}")
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
        try:
            from app.pipeline.stock_analytics import record_source_completed
            record_source_completed(job_id, clip_count)
        except Exception as analytics_err:
            print(f"[StockAnalytics] Completion hook failed: {analytics_err}")
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
        # Always purge source_videos/{job_id}/ — uploaded for Modal, never needed
        # after pipeline finishes (success or failure).
        try:
            from app.services.r2_client import delete_prefix
            n = delete_prefix(f"source_videos/{job_id}/")
            if n:
                print(f"[Orchestrator] finally: removed {n} source_videos objects")
        except Exception as _e:
            print(f"[Orchestrator] finally: source_videos cleanup error: {_e}")
        # Always cleanup transient R2 objects — success or failure
        try:
            _cleanup_pipeline_r2(job_id, exported_clips, reframed_clips, captioned_clips)
        except Exception as _ce:
            print(f"[Orchestrator] finally: R2 cleanup error (non-critical): {_ce}")
        # gaming-reframe/ prefix — always delete, never needed after pipeline
        try:
            from app.services.r2_client import delete_prefix
            n = delete_prefix(f"gaming-reframe/{job_id}/")
            if n:
                print(f"[Orchestrator] finally: removed {n} gaming-reframe objects")
        except Exception as _e:
            print(f"[Orchestrator] finally: gaming-reframe cleanup error: {_e}")
