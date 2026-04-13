"""
Reframe FFmpeg Renderer — modular, parametric.

Converts reframe analysis results (keyframes, crop coordinates) into
actual 9:16 (or other aspect ratio) MP4 files via FFmpeg.

Two render paths:
  - render_podcast_reframe: keyframes + scene_cuts → crop+scale per segment → concat
  - render_gaming_reframe: webcam crop + game crop → vstack (moved from gaming_pipeline)

These functions accept ONLY coordinates/parameters — no detection logic inside.
Both the pipeline (S09) and a future manual editor API call the same functions.
"""
import json
import logging
import os
import subprocess
from typing import Optional

from .types import ReframeKeyframe

logger = logging.getLogger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _clamp_crop_expr(expr: str, low: int, high: int) -> str:
    """
    Clamp a crop coordinate expression to [low, high].

    Static values (plain numbers from stationary segments) are clamped in Python
    — no FFmpeg functions needed, no comma issues.

    Dynamic expressions (panning segments with 't' variable) are wrapped in
    FFmpeg min(max()) with ALL commas escaped as \\, so the filter_complex
    parser treats them as literal characters, not filter-chain separators.
    FFmpeg unescapes \\, → , before the expression evaluator runs.
    """
    try:
        val = float(expr)
        return str(round(max(low, min(val, high)), 1))
    except ValueError:
        escaped = expr.replace(",", "\\,")
        return f"min(max({escaped}\\,{low})\\,{high})"


# ─── Podcast / Single / Generic Reframe ──────────────────────────────────────

def render_podcast_reframe(
    video_path: str,
    keyframes: list[ReframeKeyframe],
    scene_cuts: list[float],
    src_w: int,
    src_h: int,
    crop_w: int,
    crop_h: int,
    fps: float,
    duration_s: float,
    output_path: str,
    canvas_w: int = 1080,
    canvas_h: int = 1920,
) -> str:
    """
    Render a podcast-style reframe: crop+scale each segment, concat into final MP4.

    Segments are defined by scene_cuts. Each segment gets the crop position from
    its first keyframe (hold keyframe at the cut boundary). Within-segment panning
    keyframes are interpolated via FFmpeg crop expressions.

    Args:
        video_path: Source 16:9 video
        keyframes: ReframeKeyframe list (offset_x, offset_y, time_s, interpolation)
        scene_cuts: Timestamps where hard cuts happen (scene boundaries)
        src_w, src_h: Source dimensions
        crop_w, crop_h: Crop window size (pre-computed from aspect ratio)
        fps: Video frame rate
        duration_s: Total video duration
        output_path: Where to write the rendered MP4
        canvas_w, canvas_h: Output canvas dimensions

    Returns: output_path
    """
    if not keyframes:
        raise ValueError("No keyframes provided for podcast reframe render")

    # Build segments from scene_cuts
    segments = _build_segments(keyframes, scene_cuts, duration_s, fps)
    logger.info("[Render] %d segments from %d scene cuts", len(segments), len(scene_cuts))

    # Detect audio stream — clips from S07 may be video-only
    has_audio = _has_audio_stream(video_path)
    logger.info("[Render] Audio stream: %s", "yes" if has_audio else "no (video-only)")

    n = len(segments)
    logger.info("[Render] Podcast render: %d segments, crop=%dx%d → %dx%d", n, crop_w, crop_h, canvas_w, canvas_h)

    # Render each segment individually then concat.
    # A single filter_complex with split=N becomes unreliable beyond ~10 segments:
    # FFmpeg's filter graph configuration fails with "Error reinitializing filters!"
    # when N is large (e.g., 22 segments from a dense podcast). Per-segment rendering
    # + lossless concat is far more stable.
    tmp_files = []
    concat_list_path = output_path + ".concat.txt"

    try:
        for i, seg in enumerate(segments):
            tmp_path = output_path + f".seg{i}.mp4"
            tmp_files.append(tmp_path)

            crop_x_expr = _build_crop_expression(seg["keyframes"], "offset_x", seg["start"], fps)
            crop_y_expr = _build_crop_expression(seg["keyframes"], "offset_y", seg["start"], fps)
            crop_x_expr = _clamp_crop_expr(crop_x_expr, 0, src_w - crop_w)
            crop_y_expr = _clamp_crop_expr(crop_y_expr, 0, src_h - crop_h)

            duration = seg["end"] - seg["start"]
            vf = (
                f"crop={crop_w}:{crop_h}:{crop_x_expr}:{crop_y_expr},"
                f"scale={canvas_w}:{canvas_h}:flags=lanczos"
            )

            # Use input-side seek (-ss before -i) for fast decode; timestamps reset
            # to 0 so the 't' variable in crop expressions starts at 0 per segment —
            # which matches what _build_crop_expression produces (subtracts seg start).
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{seg['start']:.6f}",
                "-t", f"{duration:.6f}",
                "-i", video_path,
                "-vf", vf,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-movflags", "+faststart",
            ]
            if has_audio:
                cmd.extend(["-c:a", "aac", "-b:a", "320k"])
            cmd.append(tmp_path)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg segment {i} render failed.\n"
                    f"stderr={result.stderr[-600:]}"
                )
            logger.info("[Render] Segment %d/%d done (%.2fs–%.2fs)", i + 1, n, seg["start"], seg["end"])

        # Write concat list and join all segments losslessly
        with open(concat_list_path, "w") as f:
            for p in tmp_files:
                f.write(f"file '{p}'\n")

        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            output_path,
        ]
        result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg concat failed.\n"
                f"stderr={result.stderr[-600:]}"
            )

    finally:
        for p in tmp_files:
            if os.path.exists(p):
                os.remove(p)
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)

    logger.info("[Render] Podcast render complete: %s", output_path)
    return output_path


def _build_segments(
    keyframes: list[ReframeKeyframe],
    scene_cuts: list[float],
    duration_s: float,
    fps: float,
) -> list[dict]:
    """
    Build segments from scene cuts. Each segment gets its relevant keyframes.
    Same logic as the frontend applyReframeWithSplits.
    """
    snap = lambda t: round(round(t * fps) / fps, 6)

    # Filter and snap scene cuts
    valid_cuts = sorted(set(snap(c) for c in scene_cuts if 0 < c < duration_s))

    boundaries = [0.0] + valid_cuts + [duration_s]
    sorted_kfs = sorted(keyframes, key=lambda kf: kf.time_s)
    frame_tol = 1.5 / fps

    segments = []
    for s in range(len(boundaries) - 1):
        seg_start = boundaries[s]
        seg_end = boundaries[s + 1]

        # Find anchor keyframe for this segment
        if s == 0:
            anchor = sorted_kfs[0] if sorted_kfs else None
        else:
            cut_time = valid_cuts[s - 1]
            # Hold keyframe at cut boundary (new shot position)
            holds = [kf for kf in sorted_kfs
                     if kf.interpolation == "hold" and abs(kf.time_s - cut_time) < frame_tol]
            anchor = holds[-1] if holds else None

        # Collect linear keyframes within this segment
        if s == 0:
            linear_kfs = [kf for kf in sorted_kfs
                          if kf.interpolation == "linear"
                          and kf.time_s >= seg_start - 0.5 / fps
                          and kf.time_s <= seg_end + frame_tol]
        else:
            linear_kfs = [kf for kf in sorted_kfs
                          if kf.interpolation == "linear"
                          and kf.time_s > seg_start
                          and kf.time_s <= seg_end + frame_tol]

        # Build segment keyframe list
        if s == 0:
            seg_kfs = linear_kfs if linear_kfs else ([anchor] if anchor else [])
        else:
            seg_kfs = ([anchor] + linear_kfs) if anchor else linear_kfs

        # Fallback: use the last known position
        if not seg_kfs and segments:
            prev_kfs = segments[-1]["keyframes"]
            if prev_kfs:
                seg_kfs = [prev_kfs[-1]]

        segments.append({
            "start": seg_start,
            "end": seg_end,
            "keyframes": seg_kfs,
        })

    return segments


def _build_crop_expression(
    keyframes: list[ReframeKeyframe],
    field: str,
    segment_start: float,
    fps: float,
) -> str:
    """
    Build an FFmpeg expression that linearly interpolates between keyframes.
    For static segments (1 keyframe), returns a simple constant.
    For panning segments, returns a chain of if(between(t,...)) expressions.
    """
    if not keyframes:
        return "0"

    values = [getattr(kf, field, 0.0) or 0.0 for kf in keyframes]

    # Check if all values are the same (static segment)
    if len(set(round(v, 1) for v in values)) <= 1:
        return str(round(values[0], 1))

    if len(keyframes) == 1:
        return str(round(values[0], 1))

    # Build piecewise linear expression
    # t in FFmpeg trim+setpts is relative to segment start (PTS-STARTPTS)
    parts = []
    for i in range(len(keyframes) - 1):
        t1 = keyframes[i].time_s - segment_start
        t2 = keyframes[i + 1].time_s - segment_start
        v1 = values[i]
        v2 = values[i + 1]
        dt = t2 - t1

        if dt <= 0 or abs(v2 - v1) < 0.5:
            # No movement in this interval
            parts.append((t1, t2, str(round(v1, 1))))
        else:
            # Linear interpolation: v1 + (v2-v1) * (t-t1) / (t2-t1)
            expr = f"{v1:.1f}+{v2 - v1:.1f}*(t-{t1:.4f})/{dt:.4f}"
            parts.append((t1, t2, expr))

    # Build chained if(between(t,...)) expression
    if len(parts) == 1:
        return parts[0][2]

    # Chain: if(lt(t,t2), expr1, if(lt(t,t3), expr2, ..., exprN))
    result = parts[-1][2]  # Last interval as default
    for i in range(len(parts) - 2, -1, -1):
        t_end = parts[i][1]
        result = f"if(lt(t,{t_end:.4f}),{parts[i][2]},{result})"

    return result


# ─── Gaming Reframe ──────────────────────────────────────────────────────────

def render_gaming_vstack(
    input_path: str,
    output_path: str,
    wc_x: int, wc_y: int, wc_w: int, wc_h: int,
    game_x: int, game_y: int, game_w: int, game_h: int,
    output_w: int = 1080,
    webcam_h: int = 640,
    game_h_out: int = 1280,
) -> None:
    """
    Render 1080x1920 split-screen video via FFmpeg filter_complex vstack.

    Top panel:    webcam crop → scale to output_w × webcam_h
    Bottom panel: game crop   → scale to output_w × game_h_out
    """
    webcam_filter = (
        f"[0:v]crop={wc_w}:{wc_h}:{wc_x}:{wc_y},"
        f"scale={output_w}:{webcam_h}"
        "[top]"
    )
    game_filter = (
        f"[0:v]crop={game_w}:{game_h}:{game_x}:{game_y},"
        f"scale={output_w}:{game_h_out}"
        "[bottom]"
    )

    filter_complex = f"{webcam_filter};{game_filter};[top][bottom]vstack=inputs=2[out]"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "320k",
        "-movflags", "+faststart",
        output_path,
    ]

    logger.info(
        "[Render] Gaming vstack: wc=crop(%d:%d:%d:%d) game=crop(%d:%d:%d:%d)",
        wc_w, wc_h, wc_x, wc_y, game_w, game_h, game_x, game_y,
    )

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg gaming render failed: {result.stderr[-800:]}")

    logger.info("[Render] Gaming vstack complete: %s", output_path)


# ─── Audio detection ──────────────────────────────────────────────────────────

def _has_audio_stream(video_path: str) -> bool:
    """Return True if the video file contains at least one audio stream."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a:0",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return False
        data = json.loads(result.stdout)
        return len(data.get("streams", [])) > 0
    except Exception as e:
        logger.warning("[Render] Audio stream probe failed (%s) — assuming audio present", e)
        return True
