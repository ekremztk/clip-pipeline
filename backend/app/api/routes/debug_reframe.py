"""
Debug endpoints — reframe testing and diagnostics.

POST /debug/reframe-test      → full render (S09 pipeline)
POST /debug/reframe-diagnose  → analysis only, NO render, every step logged

Remove this file when testing is done.
"""
import json
import os
import re
import subprocess
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/debug", tags=["debug"])


class ReframeTestRequest(BaseModel):
    clip_url: str


# ─── Full render test ─────────────────────────────────────────────────────────

@router.post("/reframe-test")
def reframe_test(req: ReframeTestRequest):
    from app.pipeline.steps.s09_reframe import _reframe_podcast

    if not req.clip_url:
        raise HTTPException(status_code=400, detail="clip_url required")

    try:
        reframed_url, metadata = _reframe_podcast(
            clip_url=req.clip_url,
            job_id="",
            clip_index=0,
        )
        return {"reframed_url": reframed_url, "metadata": metadata}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Diagnostic — no render ───────────────────────────────────────────────────

@router.post("/reframe-diagnose")
def reframe_diagnose(req: ReframeTestRequest):
    """
    Full pipeline analysis WITHOUT rendering.

    For every scene cut this returns:
      - raw pts_time detected by FFmpeg showinfo
      - snapped cut_time (shot detector output)
      - cut_frame under 3 formulas:
          * original:    round(cut_time * fps)
          * container:   round((cut_time - ffprobe_start_time) * fps)   ← current fix
          * first_frame: round((cut_time - first_frame_pts) * fps)      ← correct formula
      - n_actual: real 0-indexed frame number derived from first_frame_pts

    Also returns per-segment keyframe assignments and the generated
    FFmpeg crop expression so the exact boundaries can be verified.
    """
    from app.pipeline.steps.s09_reframe import _download_temp
    from app.reframe.pipeline import run_reframe
    from app.reframe.render import (
        _build_segments, _build_crop_expression,
        _chain_segments, _clamp_crop_expr, _get_start_pts,
    )
    from app.config import settings

    if not req.clip_url:
        raise HTTPException(status_code=400, detail="clip_url required")

    local_path = _download_temp(req.clip_url)
    try:
        # ── Step 1: Video metadata ────────────────────────────────────────────
        video_meta = _diag_probe_video(local_path)
        fps = video_meta["fps"]
        src_w = video_meta["width"]
        src_h = video_meta["height"]

        # ── Step 2: Actual first-frame PTS from filter graph ──────────────────
        first_frame_pts = _diag_get_first_frame_pts(local_path)
        container_start_time = _get_start_pts(local_path)  # current (potentially wrong) value

        # ── Step 3: Raw scene detection — pts_time BEFORE snapping ───────────
        raw_scene_data = _diag_raw_scene_detect(local_path, fps)

        # ── Step 4: Full reframe pipeline → keyframes + scene_cuts ───────────
        result = run_reframe(
            clip_local_path=local_path,
            job_id="",
            strategy="podcast",
            aspect_ratio="9:16",
            tracking_mode="x_only",
            content_type_hint="podcast",
            detection_engine="yolo",
        )
        crop_w = result.metadata.get("crop_w", 0)
        crop_h = result.metadata.get("crop_h", 0)

        # ── Step 5: Cut-frame analysis for each scene cut ────────────────────
        cut_frame_analysis = []
        for cut_time in result.scene_cuts:
            frame_original = round(cut_time * fps)
            frame_container = round((cut_time - container_start_time) * fps)
            frame_firstpts = round((cut_time - first_frame_pts) * fps)
            # n_actual: which real video frame (0-indexed) this cut_time maps to
            n_actual = round((cut_time - first_frame_pts) * fps)
            cut_frame_analysis.append({
                "cut_time_s": round(cut_time, 6),
                "formulas": {
                    "original_round(cut*fps)": frame_original,
                    "container_start_corrected": frame_container,
                    "first_frame_pts_corrected": frame_firstpts,
                },
                "n_actual_0indexed": n_actual,
                "currently_used_cut_frame": frame_container,
                "correct_cut_frame": frame_firstpts,
                "error_frames": frame_container - frame_firstpts,
            })

        # ── Step 6: Segment assignment ────────────────────────────────────────
        segments = _build_segments(result.keyframes, result.scene_cuts, result.duration_s, fps)

        seg_details = []
        for i, seg in enumerate(segments):
            ex = _build_crop_expression(seg["keyframes"], "offset_x", 0.0, fps)
            ey = _build_crop_expression(seg["keyframes"], "offset_y", 0.0, fps)
            ex_clamped = _clamp_crop_expr(ex, 0, src_w - crop_w) if crop_w else ex
            ey_clamped = _clamp_crop_expr(ey, 0, src_h - crop_h) if crop_h else ey
            seg_details.append({
                "index": i,
                "start_s": round(seg["start"], 4),
                "end_s": round(seg["end"], 4),
                "keyframe_count": len(seg["keyframes"]),
                "keyframes": [
                    {
                        "t": round(kf.time_s, 4),
                        "x": kf.offset_x,
                        "y": kf.offset_y,
                        "interp": kf.interpolation,
                    }
                    for kf in seg["keyframes"]
                ],
                "x_expr_raw": ex,
                "x_expr_clamped": ex_clamped,
                "y_expr_clamped": ey_clamped,
            })

        # ── Step 7: Build crop expression with current fix ───────────────────
        seg_x = []
        for seg in segments:
            ex = _build_crop_expression(seg["keyframes"], "offset_x", 0.0, fps)
            ex = _clamp_crop_expr(ex, 0, src_w - crop_w) if crop_w else ex
            seg_x.append((seg["start"], seg["end"], ex))

        crop_x_current = _chain_segments(seg_x, fps, container_start_time)
        crop_x_correct = _chain_segments(seg_x, fps, first_frame_pts)
        crop_x_original = _chain_segments(seg_x, fps, 0.0)

        # Trim expressions for readability (first 300 chars)
        def _trim(s: str) -> str:
            return s[:300] + "…" if len(s) > 300 else s

        return {
            "step1_video_meta": video_meta,
            "step2_pts_offsets": {
                "first_frame_pts_s": first_frame_pts,
                "container_start_time_s": container_start_time,
                "difference_s": round(container_start_time - first_frame_pts, 6),
                "difference_frames": round((container_start_time - first_frame_pts) * fps, 2),
            },
            "step3_raw_scene_detection": raw_scene_data,
            "step4_pipeline": {
                "keyframe_count": len(result.keyframes),
                "scene_cut_count": len(result.scene_cuts),
                "scene_cuts": result.scene_cuts,
                "crop_w": crop_w,
                "crop_h": crop_h,
                "src_w": src_w,
                "src_h": src_h,
            },
            "step5_cut_frame_analysis": cut_frame_analysis,
            "step6_segments": seg_details,
            "step7_crop_expressions": {
                "original_no_correction": _trim(crop_x_original),
                "current_fix_container_start": _trim(crop_x_current),
                "correct_first_frame_pts": _trim(crop_x_correct),
            },
            "verdict": _build_verdict(cut_frame_analysis, first_frame_pts, container_start_time),
        }

    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{e}\n{traceback.format_exc()}")
    finally:
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass


# ─── Diagnostic helpers ───────────────────────────────────────────────────────

def _diag_probe_video(video_path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "v:0", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    data = json.loads(result.stdout)
    s = data["streams"][0]
    fps_str = s.get("r_frame_rate", "25/1")
    num, den = fps_str.split("/")
    fps = float(num) / float(den)
    return {
        "width": s.get("width"),
        "height": s.get("height"),
        "fps": fps,
        "fps_str": fps_str,
        "nb_frames": int(s.get("nb_frames") or 0),
        "codec_name": s.get("codec_name"),
        "start_pts": s.get("start_pts"),
        "start_time_ffprobe": float(s.get("start_time") or 0),
        "time_base": s.get("time_base"),
        "duration_s": float(s.get("duration") or 0),
    }


def _diag_get_first_frame_pts(video_path: str) -> float:
    """
    Get the pts_time of the FIRST DECODED FRAME from the filter graph.
    This is the correct offset for converting cut_time → cut_frame (n).

    Different from ffprobe start_time: for videos with B-frame delay or
    non-standard edit lists, the first decoded frame's PTS ≠ container start_time.
    """
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_frames", "-select_streams", "v:0",
        "-read_intervals", "%+#1",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout)
        frames = data.get("frames", [])
        if frames:
            return float(frames[0].get("pts_time") or 0.0)
    except Exception:
        pass
    return 0.0


def _diag_raw_scene_detect(video_path: str, fps: float) -> list:
    """
    Run scene detection and capture both:
      - raw pts_time from FFmpeg showinfo (before any snapping)
      - the snapped value (what the shot detector emits)
    Also compute what n (0-indexed filter frame counter) each cut maps to.
    """
    first_frame_pts = _diag_get_first_frame_pts(video_path)
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", "select='gt(scene,0.35)',showinfo",
        "-vsync", "0", "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    cuts = []
    for match in re.finditer(r"pts_time:([\d.]+)", result.stderr):
        pts_time = float(match.group(1))
        snapped = round(round(pts_time * fps) / fps, 6)
        n_correct = round((pts_time - first_frame_pts) * fps)
        n_original = round(pts_time * fps)
        cuts.append({
            "raw_pts_time_s": pts_time,
            "snapped_cut_time_s": snapped,
            "n_correct_cut_frame": n_correct,
            "n_original_formula": n_original,
            "error_frames": n_original - n_correct,
        })
    return cuts


def _build_verdict(cut_frame_analysis: list, first_frame_pts: float, container_start_time: float) -> dict:
    if not cut_frame_analysis:
        return {"status": "no_cuts"}

    errors_current = [abs(c["error_frames"]) for c in cut_frame_analysis]
    errors_correct = [0 for _ in cut_frame_analysis]  # by definition
    max_err_current = max(errors_current) if errors_current else 0

    if max_err_current == 0:
        status = "CORRECT — current formula matches first_frame_pts"
    else:
        status = f"WRONG — current formula is off by up to {max_err_current} frame(s)"

    fps_approx = cut_frame_analysis[0]["formulas"]["original_round(cut*fps)"] / max(cut_frame_analysis[0]["cut_time_s"], 0.001) if cut_frame_analysis else 25.0
    return {
        "status": status,
        "first_frame_pts_s": first_frame_pts,
        "container_start_time_s": container_start_time,
        "pts_offset_error_frames": round((container_start_time - first_frame_pts) * fps_approx, 2),
        "recommended_fix": "use first_frame_pts (ffprobe -show_frames first frame) instead of container start_time",
    }
