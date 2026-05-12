"""
Reframe V5 — Main orchestrator.

Pipeline steps:
  1. ffprobe → video metadata
  2. shot_detector → shot boundaries (FFmpeg scene filter)
  3. face_tracker → per-frame face detections (YOLO)
  4. gemini_director → high-level creative plan
  5. focus_resolver → merge Gemini + detections → focus points
  6. path_solver → smooth camera paths (AutoFlip algorithm)
  7. keyframe_emitter → pixel offsets for frontend

Fallback: if Gemini fails, step 4 uses diarization-only plan.
"""
import json
import logging
import os
import subprocess
import uuid
from typing import Callable, Optional

import requests

from app.config import settings

from .config import ReframeConfig
from .shot_detector import detect_shots
from .face_tracker import (
    analyze_video as track_faces,
    classify_shots,
    normalize_detection_engine,
    parse_detection_engine_spec,
)
from .gemini_director import analyze_video as gemini_analyze, build_fallback_plan
from .focus_resolver import resolve_focus
from .path_solver import solve_paths
from .keyframe_emitter import emit_keyframes
from .types import Frame, ReframeResult, Shot

logger = logging.getLogger(__name__)


def _configure_reframe_logging() -> None:
    """Ensure all reframe module loggers emit at INFO level."""
    reframe_logger = logging.getLogger("app.reframe")
    if not reframe_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        ))
        reframe_logger.addHandler(handler)
    reframe_logger.setLevel(logging.INFO)


def run_reframe(
    clip_url: Optional[str] = None,
    clip_local_path: Optional[str] = None,
    clip_id: Optional[str] = None,
    job_id: Optional[str] = None,
    clip_start: float = 0.0,
    clip_end: Optional[float] = None,
    strategy: str = "auto",
    aspect_ratio: str = "9:16",
    tracking_mode: str = "dynamic_xy",
    content_type_hint: Optional[str] = None,
    detection_engine: str = "yolo",
    on_progress: Optional[Callable[[str, int], None]] = None,
    debug_mode: bool = False,
) -> ReframeResult:
    """
    V5 reframe pipeline.
    Function signature unchanged from V4 — frontend needs no changes.
    """
    engine_mode, engine_list = parse_detection_engine_spec(detection_engine)
    if engine_mode == "compare":
        return _run_reframe_comparison(
            clip_url=clip_url,
            clip_local_path=clip_local_path,
            clip_id=clip_id,
            job_id=job_id,
            clip_start=clip_start,
            clip_end=clip_end,
            strategy=strategy,
            aspect_ratio=aspect_ratio,
            tracking_mode=tracking_mode,
            content_type_hint=content_type_hint,
            detection_engines=engine_list,
            on_progress=on_progress,
            debug_mode=debug_mode,
        )

    detection_engine = normalize_detection_engine(engine_list[0])
    _configure_reframe_logging()

    if not clip_url and not clip_local_path:
        raise ValueError("clip_url or clip_local_path required")

    def progress(step: str, pct: int) -> None:
        logger.info("[Reframe] %d%% — %s", pct, step)
        if on_progress:
            on_progress(step, pct)

    # Config
    ar_tuple = _parse_aspect_ratio(aspect_ratio)
    config = ReframeConfig(
        aspect_ratio=ar_tuple,
        tracking_mode=tracking_mode,
    )
    if content_type_hint and content_type_hint != "auto":
        config.gemini_director.content_type_hint = content_type_hint

    temp_path: Optional[str] = None

    # Resolve input
    if clip_local_path and os.path.exists(clip_local_path):
        input_path = clip_local_path
    else:
        temp_path = os.path.join(
            str(settings.UPLOAD_DIR),
            f"reframe_{uuid.uuid4().hex}.mp4",
        )
        input_path = temp_path

    try:
        # 1. Download (if needed)
        if temp_path:
            progress("Downloading video...", 5)
            _download_video(clip_url, temp_path)

        # 2. Video metadata
        progress("Reading video metadata...", 8)
        src_w, src_h, fps, duration_s = _probe_video(input_path)
        logger.info("[Reframe] %dx%d @ %.2ffps, %.2fs", src_w, src_h, fps, duration_s)

        effective_end = clip_end if clip_end is not None else duration_s

        # Gaming mode: server-side FFmpeg vstack render — no Gemini, no diarization
        if content_type_hint == "gaming":
            from .gaming_pipeline import run_gaming_reframe
            result = run_gaming_reframe(
                video_path=input_path,
                src_w=src_w,
                src_h=src_h,
                fps=fps,
                duration_s=duration_s,
                detection_engine=detection_engine,
                enable_debug=debug_mode,
                on_progress=on_progress,
            )
            return result
            # Note: temp_path cleanup is handled by the outer finally block

        # 3. Shot detection
        progress("Detecting scene cuts...", 12)
        raw_shots = detect_shots(input_path, duration_s, config.shot_detection, fps)
        logger.info("[Reframe] %d raw shots detected", len(raw_shots))

        # 4. Build the final scene list before the production tracking pass.
        # A preliminary face pass is allowed to classify and merge false cuts,
        # but Gemini and rendering only ever see detections from final shots.
        engine_label = detection_engine.upper()
        shots = raw_shots
        preliminary_frames: list[Frame] = []

        if len(raw_shots) > 1:
            progress(f"Pre-scanning scene layout ({engine_label})...", 18)
            preliminary_frames = track_faces(
                input_path,
                raw_shots,
                src_w,
                src_h,
                config.face_tracker,
                engine_type=detection_engine,
            )
            classify_shots(raw_shots, preliminary_frames)
            shots = _merge_false_cuts(raw_shots, preliminary_frames)

        false_cut_merges = max(0, len(raw_shots) - len(shots))
        if false_cut_merges:
            logger.info("[Reframe] Final scene list merged %d false cuts", false_cut_merges)

        needs_final_tracking = not preliminary_frames or not _same_shots(raw_shots, shots)
        if needs_final_tracking:
            progress(f"Tracking faces on final scenes ({engine_label})...", 24)
            frames = track_faces(
                input_path,
                shots,
                src_w,
                src_h,
                config.face_tracker,
                engine_type=detection_engine,
            )
            progress("Classifying final scenes...", 35)
            classify_shots(shots, frames)
        else:
            frames = preliminary_frames

        logger.info("[Reframe] %d final frames analyzed (engine=%s)", len(frames), detection_engine)
        for s in shots:
            logger.info("[Reframe] Shot %.1f-%.1fs: %s (%.1fs)", s.start_s, s.end_s, s.shot_type, s.duration_s)

        # 6. Load diarization
        progress("Loading speaker data...", 40)
        diarization: list[dict] = []
        if job_id:
            try:
                diarization = _load_diarization(job_id, clip_start, effective_end)
                logger.info("[Reframe] %d diarization segments for job_id=%s", len(diarization), job_id)
            except Exception as e:
                logger.warning("[Reframe] Diarization failed: %s — visual only", e)
        else:
            logger.warning("[Reframe] No job_id — visual only mode")

        # 7. Render numbered-person video for Gemini, then get creative direction
        progress("Preparing AI analysis...", 48)
        gemini_video_path: Optional[str] = None
        try:
            from .debug_overlay import generate_gemini_video
            gemini_video_path = os.path.join(
                str(settings.UPLOAD_DIR),
                f"gemini_numbered_{uuid.uuid4().hex}.mp4",
            )
            generate_gemini_video(
                input_path=input_path,
                src_w=src_w,
                src_h=src_h,
                fps=fps,
                frames=frames,
                output_path=gemini_video_path,
            )
            logger.info("[Reframe] Gemini numbered video ready: %s", gemini_video_path)
        except Exception as e:
            logger.warning("[Reframe] Gemini numbered video failed: %s — using original", e)
            gemini_video_path = None

        progress("AI analyzing video...", 50)
        try:
            director_plan = gemini_analyze(
                video_path=gemini_video_path or input_path,
                diarization_segments=diarization,
                shots=shots,
                frames=frames,
                src_w=src_w,
                src_h=src_h,
                fps=fps,
                duration_s=duration_s,
                aspect_ratio=ar_tuple,
                config=config.gemini_director,
            )
        except Exception as e:
            logger.warning("[Reframe] Gemini failed: %s — using fallback", e)
            director_plan = build_fallback_plan(diarization, shots, duration_s)
        finally:
            if gemini_video_path and os.path.exists(gemini_video_path):
                try:
                    os.remove(gemini_video_path)
                except Exception:
                    pass

        result_content_type = director_plan.content_type

        # 8. Focus resolver
        progress("Resolving focus targets...", 65)
        focus_points = resolve_focus(director_plan, frames, shots, config.focus_resolver)

        # 9. Path solver (AutoFlip kinematic)
        progress("Computing smooth camera paths...", 75)
        logger.info(
            "[Reframe] solve_paths: %d focus_points, %d shots, fps=%.2f",
            len(focus_points), len(shots), fps,
        )
        try:
            shot_paths = solve_paths(focus_points, shots, fps, config.path_solver)
        except Exception as path_err:
            logger.error("[Reframe] solve_paths FAILED: %s", path_err, exc_info=True)
            raise
        logger.info("[Reframe] solve_paths complete: %d shot paths", len(shot_paths))

        # 10. Keyframe emission
        progress("Generating keyframes...", 85)
        result = emit_keyframes(
            shot_paths=shot_paths,
            shots=shots,
            src_w=src_w,
            src_h=src_h,
            fps=fps,
            duration_s=duration_s,
            config=config,
        )

        result.content_type = result_content_type
        result.metadata["raw_shot_count"] = len(raw_shots)
        result.metadata["final_shot_count"] = len(shots)
        result.metadata["false_cut_merge_count"] = false_cut_merges
        result.metadata["detection_engine"] = detection_engine
        result.metadata["detector_quality"] = _build_detector_quality_summary(
            frames,
            shots,
            sample_fps=config.face_tracker.sample_fps,
        )

        # Attach full pipeline decisions to metadata for debug analyzer
        result.metadata["pipeline_decisions"] = _build_pipeline_decisions(
            shots, frames, director_plan, focus_points, shot_paths,
            diarization, src_w, src_h, fps, duration_s,
        )

        # Debug mode: generate overlay video and upload to R2
        if debug_mode:
            try:
                progress("Generating debug video...", 92)
                from .debug_overlay import generate_debug_video
                from app.services.r2_client import get_r2_client
                from app.config import settings as s

                # Get crop dimensions from result metadata
                crop_w = result.metadata.get("crop_w", 0)
                crop_h = result.metadata.get("crop_h", 0)

                debug_path = generate_debug_video(
                    input_path=input_path,
                    src_w=src_w,
                    src_h=src_h,
                    fps=fps,
                    shots=shots,
                    frames=frames,
                    focus_points=focus_points,
                    shot_paths=shot_paths,
                    keyframes=result.keyframes,
                    crop_w=crop_w,
                    crop_h=crop_h,
                    engine_name=detection_engine,
                )

                # Upload to R2
                r2 = get_r2_client()
                debug_key = f"debug/reframe_debug_{uuid.uuid4().hex}.mp4"
                with open(debug_path, "rb") as f:
                    r2.put_object(
                        Bucket=s.R2_BUCKET_NAME,
                        Key=debug_key,
                        Body=f,
                        ContentType="video/mp4",
                    )
                debug_url = f"{s.R2_PUBLIC_URL}/{debug_key}"
                result.metadata["debug_video_url"] = debug_url
                logger.info("[Reframe] Debug video uploaded: %s", debug_url)

                # Clean up local debug file
                try:
                    os.remove(debug_path)
                except Exception:
                    pass

            except Exception as e:
                logger.error("[Reframe] Debug video generation failed: %s", e)

        progress("Done!", 100)
        logger.info(
            "[Reframe] Complete — %d keyframes, %d scene cuts, type=%s",
            len(result.keyframes), len(result.scene_cuts), result.content_type,
        )
        return result

    except Exception as e:
        logger.error("[Reframe] Pipeline error: %s", e)
        import traceback
        traceback.print_exc()
        raise

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def _run_reframe_comparison(
    clip_url: Optional[str],
    clip_local_path: Optional[str],
    clip_id: Optional[str],
    job_id: Optional[str],
    clip_start: float,
    clip_end: Optional[float],
    strategy: str,
    aspect_ratio: str,
    tracking_mode: str,
    content_type_hint: Optional[str],
    detection_engines: list[str],
    on_progress: Optional[Callable[[str, int], None]],
    debug_mode: bool,
) -> ReframeResult:
    _configure_reframe_logging()

    variants: list[dict] = []
    failures: list[dict] = []
    primary: Optional[ReframeResult] = None
    primary_engine = ""

    for index, engine in enumerate(detection_engines):
        if on_progress:
            on_progress(f"Detector compare {index + 1}/{len(detection_engines)}: {engine}", 5)

        try:
            result = run_reframe(
                clip_url=clip_url,
                clip_local_path=clip_local_path,
                clip_id=clip_id,
                job_id=job_id,
                clip_start=clip_start,
                clip_end=clip_end,
                strategy=strategy,
                aspect_ratio=aspect_ratio,
                tracking_mode=tracking_mode,
                content_type_hint=content_type_hint,
                detection_engine=engine,
                on_progress=on_progress,
                debug_mode=debug_mode,
            )
            variant_summary = _summarize_reframe_variant(engine, result)
            variants.append(variant_summary)
            if primary is None:
                primary = result
                primary_engine = engine
        except Exception as exc:
            logger.exception("[Reframe] Detector variant failed: %s", engine)
            failures.append({
                "engine": engine,
                "status": "error",
                "error": str(exc)[:300],
            })

    if primary is None:
        raise RuntimeError(
            "All detector comparison variants failed: "
            + ", ".join(f"{item['engine']}={item['error']}" for item in failures)
        )

    primary.metadata["detector_comparison"] = {
        "mode": "compare",
        "requested_engines": detection_engines,
        "primary_engine": primary_engine,
        "variants": variants,
        "failures": failures,
    }
    primary.metadata["detection_engine_spec"] = f"compare:{','.join(detection_engines)}"
    return primary


def _summarize_reframe_variant(engine: str, result: ReframeResult) -> dict:
    return {
        "engine": engine,
        "status": "ok",
        "keyframe_count": len(result.keyframes),
        "scene_cut_count": len(result.scene_cuts),
        "content_type": result.content_type,
        "debug_video_url": result.metadata.get("debug_video_url"),
        "raw_shot_count": result.metadata.get("raw_shot_count"),
        "final_shot_count": result.metadata.get("final_shot_count"),
        "false_cut_merge_count": result.metadata.get("false_cut_merge_count"),
        "detector_quality": result.metadata.get("detector_quality"),
    }


# --- Pipeline decisions builder (for debug analyzer) ------------------------

def _build_pipeline_decisions(
    shots, frames, director_plan, focus_points, shot_paths,
    diarization, src_w, src_h, fps, duration_s,
) -> dict:
    """Collect all intermediate pipeline decisions into one dict for Gemini analysis."""
    shot_data = []
    for i, s in enumerate(shots):
        shot_frames = [f for f in frames if f.shot_index == i]
        face_counts = [len(f.faces) for f in shot_frames]
        avg_faces = round(sum(face_counts) / len(face_counts), 2) if face_counts else 0
        shot_data.append({
            "index": i,
            "start_s": round(s.start_s, 2),
            "end_s": round(s.end_s, 2),
            "duration_s": round(s.duration_s, 2),
            "type": s.shot_type,
            "frames_sampled": len(shot_frames),
            "avg_faces_per_frame": avg_faces,
            "frames_with_2plus_faces": sum(1 for c in face_counts if c >= 2),
            "frames_with_1_face": sum(1 for c in face_counts if c == 1),
            "frames_with_0_faces": sum(1 for c in face_counts if c == 0),
        })

    subjects = [{"id": s.id, "scene_track_ids": s.scene_track_ids, "description": s.description}
                for s in director_plan.subjects]
    directives = [{
        "start_s": round(d.start_s, 2), "end_s": round(d.end_s, 2),
        "subject_id": d.subject_id, "importance": d.importance, "reason": d.reason,
    } for d in director_plan.directives]

    path_summaries = [{
        "shot_index": p.shot_index,
        "strategy": p.strategy,
        "num_points": len(p.points),
        "x_range": [round(min(pt.x for pt in p.points), 3), round(max(pt.x for pt in p.points), 3)] if p.points else [],
        "y_range": [round(min(pt.y for pt in p.points), 3), round(max(pt.y for pt in p.points), 3)] if p.points else [],
    } for p in shot_paths]

    # Compute intra-shot directive switches: cases where a directive boundary falls
    # INSIDE a shot's time range (not at a shot cut). These are the events that
    # cause the path solver to teleport and the keyframe emitter to emit a hard cut
    # mid-shot. The debug analyzer uses this list to verify the hard-cut behavior.
    intra_shot_switches = []
    for d_idx in range(1, len(director_plan.directives)):
        prev_d = director_plan.directives[d_idx - 1]
        curr_d = director_plan.directives[d_idx]
        switch_time = curr_d.start_s
        # Find which shot contains this switch time
        containing_shot = None
        for s_idx, s in enumerate(shots):
            if s.start_s < switch_time < s.end_s:
                containing_shot = s_idx
                break
        if containing_shot is not None and prev_d.subject_id != curr_d.subject_id:
            intra_shot_switches.append({
                "switch_time_s": round(switch_time, 2),
                "shot_index": containing_shot,
                "from_subject": prev_d.subject_id,
                "to_subject": curr_d.subject_id,
                "shot_start_s": round(shots[containing_shot].start_s, 2),
                "shot_end_s": round(shots[containing_shot].end_s, 2),
            })

    return {
        "video": {"src_w": src_w, "src_h": src_h, "fps": round(fps, 2), "duration_s": round(duration_s, 2)},
        "shots": shot_data,
        "diarization_segments": len(diarization),
        "gemini_director": {
            "content_type": director_plan.content_type,
            "layout": director_plan.layout,
            "subjects": subjects,
            "directives": directives,
        },
        "focus_points_total": len(focus_points),
        "path_solver": path_summaries,
        "intra_shot_directive_switches": intra_shot_switches,
    }


def _build_detector_quality_summary(
    frames: list[Frame],
    shots: list[Shot],
    sample_fps: float,
) -> dict:
    face_counts = [len(frame.faces) for frame in frames]
    total_frames = len(frames)
    total_detections = sum(face_counts)
    frames_with_faces = sum(1 for count in face_counts if count > 0)
    confidences = [face.confidence for frame in frames for face in frame.faces]
    recovery_gap = 1.5 / max(sample_fps, 0.1)

    track_ids: set[tuple[int, int]] = set()
    recovered_assignments = 0
    per_shot: list[dict] = []

    for shot_idx, shot in enumerate(shots):
        shot_frames = [frame for frame in frames if frame.shot_index == shot_idx]
        shot_faces = [face for frame in shot_frames for face in frame.faces]
        shot_track_ids = sorted({face.track_id for face in shot_faces if face.track_id >= 0})
        for track_id in shot_track_ids:
            track_ids.add((shot_idx, track_id))
        recovered_assignments += sum(1 for face in shot_faces if face.track_gap_s > recovery_gap)

        per_shot.append({
            "shot_index": shot_idx,
            "type": shot.shot_type,
            "frames_sampled": len(shot_frames),
            "frames_with_faces": sum(1 for frame in shot_frames if frame.faces),
            "unique_track_count": len(shot_track_ids),
            "max_track_age": max((face.track_age for face in shot_faces), default=0),
        })

    return {
        "frames_sampled": total_frames,
        "detections_total": total_detections,
        "avg_faces_per_frame": round(total_detections / total_frames, 3) if total_frames else 0.0,
        "face_frame_coverage": round(frames_with_faces / total_frames, 3) if total_frames else 0.0,
        "empty_frame_rate": round(1.0 - frames_with_faces / total_frames, 3) if total_frames else 1.0,
        "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "unique_track_count": len(track_ids),
        "recovered_assignments": recovered_assignments,
        "shots": per_shot,
    }


# --- False cut detection -----------------------------------------------------

def _same_shots(left: list[Shot], right: list[Shot]) -> bool:
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if abs(a.start_s - b.start_s) > 0.001:
            return False
        if abs(a.end_s - b.end_s) > 0.001:
            return False
    return True


def _merge_false_cuts(
    shots: list[Shot],
    frames: list[Frame],
) -> list[Shot]:
    """Merge adjacent shots with same type + similar face count (false positives)."""
    if len(shots) <= 1:
        return shots

    def _avg_face_count(shot_idx: int) -> float:
        counts = [len(f.faces) for f in frames if f.shot_index == shot_idx]
        return sum(counts) / len(counts) if counts else 0.0

    merged: list[Shot] = [shots[0]]
    for i in range(1, len(shots)):
        prev = merged[-1]
        curr = shots[i]

        same_type = prev.shot_type == curr.shot_type
        similar_faces = abs(_avg_face_count(i - 1) - _avg_face_count(i)) < 0.5
        is_short = curr.duration_s < 1.0

        if same_type and similar_faces and is_short:
            logger.info(
                "[Reframe] Merging false cut: %.1f-%.1fs + %.1f-%.1fs",
                prev.start_s, prev.end_s, curr.start_s, curr.end_s,
            )
            merged[-1] = Shot(start_s=prev.start_s, end_s=curr.end_s, shot_type=prev.shot_type)
        else:
            merged.append(curr)

    return merged


# --- Video helpers -----------------------------------------------------------

def _probe_video(video_path: str) -> tuple[int, int, float, float]:
    """Get video dimensions, FPS and duration via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        video_path,
    ]
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error: {result.stderr[:200]}")

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError("ffprobe found no video stream")

    stream = streams[0]
    src_w = int(stream.get("width", 0))
    src_h = int(stream.get("height", 0))
    if src_w == 0 or src_h == 0:
        raise RuntimeError(f"Invalid video dimensions: {src_w}x{src_h}")

    r_frame_rate = stream.get("r_frame_rate", "30/1")
    try:
        num, den = r_frame_rate.split("/")
        fps = float(num) / float(den)
    except Exception:
        fps = 30.0

    # Prefer nb_frames/fps: more accurate than container duration field,
    # which can omit the last frame's duration (e.g. 17.00s instead of 17.04s
    # for a 426-frame 25fps video). nb_frames is reliable for MP4/MOV; falls
    # back to stream.duration for containers that report nb_frames as "N/A".
    duration_s = 0.0
    nb_frames_raw = stream.get("nb_frames", "")
    if nb_frames_raw and nb_frames_raw != "N/A" and fps > 0:
        try:
            nb_frames = int(nb_frames_raw)
            if nb_frames > 0:
                duration_s = nb_frames / fps
        except (ValueError, TypeError):
            pass

    if duration_s == 0.0:
        duration_s = float(stream.get("duration", 0.0))

    if duration_s == 0.0:
        cmd2 = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ]
        r2 = subprocess.run(
            cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=30,
        )
        if r2.returncode == 0:
            fmt = json.loads(r2.stdout).get("format", {})
            duration_s = float(fmt.get("duration", 0.0))

    if duration_s == 0.0:
        raise RuntimeError("Could not determine video duration")

    return src_w, src_h, round(fps, 4), round(duration_s, 4)


def _download_video(url: str, dest_path: str) -> None:
    """Download remote video."""
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    try:
        cmd = ["ffmpeg", "-y", "-i", url, "-c", "copy", dest_path]
        subprocess.run(
            cmd, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=300,
        )
    except subprocess.CalledProcessError:
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)


def _parse_aspect_ratio(ratio_str: str) -> tuple[int, int]:
    """'9:16' -> (9, 16). Invalid -> (9, 16) fallback."""
    try:
        parts = ratio_str.strip().split(":")
        w, h = int(parts[0]), int(parts[1])
        if w > 0 and h > 0:
            return (w, h)
    except Exception:
        pass
    return (9, 16)


# --- Diarization loader ------------------------------------------------------

def _load_diarization(
    job_id: str,
    clip_start: float,
    clip_end: float,
) -> list[dict]:
    """Load diarization data from Supabase."""
    from app.services.supabase_client import get_client

    supabase = get_client()
    resp = (
        supabase.table("transcripts")
        .select("word_timestamps, speaker_map")
        .eq("job_id", job_id)
        .execute()
    )

    if not resp.data:
        logger.warning("[Diarization] Transcript not found: job_id=%s", job_id)
        return []

    row = resp.data[0]
    words = row.get("word_timestamps") or []
    speaker_map = row.get("speaker_map") or {}

    if not words:
        return []

    raw_to_index: dict[str, int] = {}
    for k, v in speaker_map.items():
        role = str(v).upper()
        raw_id = str(k)
        if role == "HOST":
            raw_to_index[raw_id] = 0
        elif role == "GUEST":
            raw_to_index[raw_id] = 1

    segments: list[dict] = []
    current_speaker = None
    current_start = None
    current_end = None

    for word in words:
        raw_speaker = str(word.get("speaker", 0))
        speaker_idx = raw_to_index.get(raw_speaker, int(raw_speaker) % 2)
        w_start = float(word.get("start", 0))
        w_end = float(word.get("end", 0))

        if speaker_idx != current_speaker:
            if current_speaker is not None and current_start is not None:
                segments.append({
                    "speaker": current_speaker,
                    "start": current_start,
                    "end": current_end,
                })
            current_speaker = speaker_idx
            current_start = w_start
            current_end = w_end
        else:
            current_end = w_end

    if current_speaker is not None and current_start is not None:
        segments.append({
            "speaker": current_speaker,
            "start": current_start,
            "end": current_end,
        })

    clip_segments: list[dict] = []
    for seg in segments:
        if seg["end"] <= clip_start or seg["start"] >= clip_end:
            continue
        clipped_start = max(0.0, seg["start"] - clip_start)
        clipped_end = min(clip_end - clip_start, seg["end"] - clip_start)
        if clipped_end > clipped_start:
            clip_segments.append({
                "speaker": seg["speaker"],
                "start": round(clipped_start, 3),
                "end": round(clipped_end, 3),
            })

    logger.info("[Diarization] %d segments (clip %.1f-%.1fs)", len(clip_segments), clip_start, clip_end)
    return clip_segments
