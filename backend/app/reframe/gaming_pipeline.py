"""
Gaming Reframe Pipeline.

Server-side FFmpeg split-screen render (1080x1920 vstack):
  - Top panel  1080x640  : Webcam overlay (letterboxed)
  - Bottom panel 1080x1280: Gameplay (center-first crop)

Steps:
  1. Sample first 5 seconds (1 fps)
  2. YOLO face detection -> small-face = webcam overlay
  3. Custom YOLO model (prognot-webcam.pt) -> exact webcam rectangle bounds
  4. Game crop: start at center, shift only if webcam overlaps
  5. FFmpeg filter_complex vstack render -> processed_video_url
  5b. If enable_debug: ALSO render annotated debug video -> debug_video_url
  6. R2 upload -> return both URLs in metadata

No Gemini, no diarization, no keyframes.
"""
import logging
import os
import statistics
import subprocess
import uuid
from typing import Callable, Optional

import cv2
import numpy as np

from app.config import settings
from app.services.r2_client import get_r2_client

from .config import FaceTrackerConfig
from .face_tracker import _get_detector
from .types import FaceDetection, ReframeResult

logger = logging.getLogger(__name__)

# --- Detection thresholds ---------------------------------------------------

WEBCAM_MAX_FACE_WIDTH_NORM = 0.20   # faces wider than this are in-game chars, not webcam
WEBCAM_MIN_FRAME_COUNT = 3          # webcam must appear in at least this many sampled frames
WEBCAM_STABILITY_RADIUS_NORM = 0.12 # face centroid must stay within this radius across frames
EDGE_MARGIN = 20                    # px safety margin from frame edges
OVERLAP_THRESHOLD = 0.15            # allow up to 15% webcam overlap before shifting game crop

# --- Output format (fixed) --------------------------------------------------

OUTPUT_W = 1080
OUTPUT_H = 1920
WEBCAM_PANEL_H = 640
GAME_PANEL_H = 1280

WEBCAM_CUSTOM_MODEL_PATH = "/root/prognot-webcam.pt"


# ─── Public entry point ──────────────────────────────────────────────────────

def run_gaming_reframe(
    video_path: str,
    src_w: int,
    src_h: int,
    fps: float,
    duration_s: float,
    detection_engine: str = "yolo",
    enable_debug: bool = False,
    on_progress: Optional[Callable[[str, int], None]] = None,
) -> ReframeResult:
    """
    Gaming pipeline: detect webcam overlay, compute game crop, render vstack.
    Returns ReframeResult with keyframes=[] and metadata["processed_video_url"] set.
    """
    def progress(step: str, pct: int) -> None:
        logger.info("[Gaming] %d%% — %s", pct, step)
        if on_progress:
            on_progress(step, pct)

    # Step 1: Sample startup frames
    progress("Sampling startup frames...", 10)
    sampled = _sample_startup_frames(video_path, n_seconds=5)
    logger.info("[Gaming] %d startup frames sampled", len(sampled))

    # Step 2: YOLO face detection -> find webcam face
    progress("Detecting webcam overlay (YOLO)...", 25)
    config = FaceTrackerConfig()
    detector = _get_detector(detection_engine, config)
    webcam_face, best_frame = _find_webcam_face(sampled, detector, config)

    if webcam_face is None or best_frame is None:
        raise RuntimeError(
            "No webcam overlay detected in the first 5 seconds. "
            "Gaming mode requires a visible streamer face-cam in a corner. "
            "If this is a screen recording without webcam, use Podcast mode."
        )

    logger.info(
        "[Gaming] Webcam face: cx=%.3f cy=%.3f fw=%.3f fh=%.3f conf=%.2f",
        webcam_face.face_x, webcam_face.face_y,
        webcam_face.face_width, webcam_face.face_height,
        webcam_face.confidence,
    )

    # Step 3: Custom YOLO model -> exact webcam overlay bounds
    progress("Detecting webcam bounds (custom YOLO model)...", 40)
    custom_result = find_webcam_bounds_yolo_custom(
        frames=[frame for _, frame in sampled],
        src_w=src_w,
        src_h=src_h,
    )

    if custom_result is not None:
        wc_x, wc_y, wc_w, wc_h = custom_result
        detected_by = "yolo_custom"
        logger.info("[Gaming] Webcam (custom YOLO): x=%d y=%d w=%d h=%d", wc_x, wc_y, wc_w, wc_h)
    else:
        wc_x, wc_y, wc_w, wc_h = _webcam_bounds_fallback(
            webcam_face.face_x, webcam_face.face_y,
            webcam_face.face_width, webcam_face.face_height,
            src_w, src_h,
        )
        detected_by = "yolo_fallback"
        logger.info("[Gaming] Webcam (YOLO fallback): x=%d y=%d w=%d h=%d", wc_x, wc_y, wc_w, wc_h)

    # Step 3b: Face-anchored webcam crop — exact 1080:640 ratio, centered on face
    # The Canny/YOLO height is unreliable (dark BG, green screen, shoulders).
    # We use only wc_w for sizing and anchor the crop on the YOLO face center.
    face_cx_px = int(webcam_face.face_x * src_w)
    face_cy_px = int(webcam_face.face_y * src_h)
    cam_x, cam_y, cam_w, cam_h = _compute_webcam_crop(
        wc_w=wc_w,
        face_cx=face_cx_px,
        face_cy=face_cy_px,
        src_w=src_w,
        src_h=src_h,
    )
    logger.info(
        "[Gaming] Webcam crop (face-anchored 90%%): x=%d y=%d w=%d h=%d ratio=%.4f",
        cam_x, cam_y, cam_w, cam_h,
        cam_w / cam_h if cam_h > 0 else 0.0,
    )

    # Step 4: Game crop — center-first, shift only if webcam overlaps
    progress("Computing game crop region (center-first)...", 55)
    game_crop_w = int(round(src_h * OUTPUT_W / GAME_PANEL_H))
    game_crop_h = src_h
    game_crop_x, game_crop_y = _compute_game_crop_x(
        src_w, game_crop_w, wc_x, wc_w,
    )
    overlap_pct = _overlap_ratio(float(game_crop_x), game_crop_w, wc_x, wc_w) * 100.0
    logger.info(
        "[Gaming] Game crop: x=%d w=%d h=%d in %dx%d",
        game_crop_x, game_crop_w, game_crop_h, src_w, src_h,
    )

    # ── Step 5: FFmpeg vstack render (ALWAYS runs) ────────────────────────────
    progress("Rendering split-screen video (FFmpeg)...", 65)
    output_path = os.path.join(
        str(settings.UPLOAD_DIR),
        f"gaming_reframe_{uuid.uuid4().hex}.mp4",
    )
    try:
        _run_ffmpeg_gaming(
            input_path=video_path,
            output_path=output_path,
            wc_x=cam_x, wc_y=cam_y, wc_w=cam_w, wc_h=cam_h,
            game_x=game_crop_x, game_y=game_crop_y,
            game_w=game_crop_w, game_h=game_crop_h,
        )
    except Exception as e:
        try:
            os.remove(output_path)
        except Exception:
            pass
        raise RuntimeError(f"FFmpeg gaming render failed: {e}") from e

    # Step 6: Upload main vstack to R2
    progress("Uploading processed video to R2...", 80)
    processed_url = ""
    try:
        r2 = get_r2_client()
        r2_key = f"gaming-reframe/{uuid.uuid4().hex}.mp4"
        with open(output_path, "rb") as f:
            r2.put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=r2_key,
                Body=f,
                ContentType="video/mp4",
            )
        processed_url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{r2_key}"
        logger.info("[Gaming] Uploaded processed video: %s", processed_url)
    finally:
        try:
            os.remove(output_path)
        except Exception:
            pass

    # ── Step 5b: Debug render (ADDITIONAL — only when enable_debug=True) ──────
    # The main vstack above is ALWAYS produced. Debug is a second optional output.
    debug_url = ""
    if enable_debug:
        progress("Rendering debug video (drawbox annotations)...", 88)
        debug_path = os.path.join(
            str(settings.UPLOAD_DIR),
            f"gaming_debug_{uuid.uuid4().hex}.mp4",
        )
        try:
            _run_ffmpeg_debug(
                input_path=video_path,
                output_path=debug_path,
                wc_x=wc_x, wc_y=wc_y, wc_w=wc_w, wc_h=wc_h,
                cam_x=cam_x, cam_y=cam_y, cam_w=cam_w, cam_h=cam_h,
                game_x=game_crop_x, game_y=game_crop_y,
                game_w=game_crop_w, game_h=game_crop_h,
                detected_by=detected_by,
                src_w=src_w, src_h=src_h,
                overlap_pct=overlap_pct,
                face_cx=face_cx_px, face_cy=face_cy_px,
            )
            r2 = get_r2_client()
            r2_key_debug = f"gaming-debug/{uuid.uuid4().hex}.mp4"
            with open(debug_path, "rb") as f:
                r2.put_object(
                    Bucket=settings.R2_BUCKET_NAME,
                    Key=r2_key_debug,
                    Body=f,
                    ContentType="video/mp4",
                )
            debug_url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{r2_key_debug}"
            logger.info("[Gaming] Debug video uploaded: %s", debug_url)
        except Exception as exc:
            logger.warning("[Gaming] Debug render failed (non-fatal): %s", exc)
        finally:
            try:
                os.remove(debug_path)
            except Exception:
                pass

    progress("Done!", 100)

    return ReframeResult(
        keyframes=[],
        scene_cuts=[],
        src_w=OUTPUT_W,
        src_h=OUTPUT_H,
        fps=fps,
        duration_s=duration_s,
        content_type="gaming",
        tracking_mode="x_only",
        metadata={
            "processed_video_url": processed_url,
            "debug_video_url": debug_url or None,
            "webcam_raw_bounds": {"x": wc_x, "y": wc_y, "w": wc_w, "h": wc_h},
            "webcam_crop":       {"x": cam_x, "y": cam_y, "w": cam_w, "h": cam_h},
            "game_bounds":       {"x": game_crop_x, "y": game_crop_y, "w": game_crop_w, "h": game_crop_h},
            "face_center":       {"x": face_cx_px, "y": face_cy_px},
            "webcam_detected_by": detected_by,
            "overlap_pct": round(overlap_pct, 1),
            "pipeline": "gaming_vstack",
            "source_w": src_w,
            "source_h": src_h,
        },
    )


# ─── Step 1: Frame sampling ──────────────────────────────────────────────────

def _sample_startup_frames(
    video_path: str,
    n_seconds: int = 5,
) -> list[tuple[float, np.ndarray]]:
    """Extract one frame per second for the first n_seconds of the video."""
    results: list[tuple[float, np.ndarray]] = []
    cap = cv2.VideoCapture(video_path)
    try:
        duration_ms = cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(cap.get(cv2.CAP_PROP_FPS), 1) * 1000
        for t in range(n_seconds):
            t_ms = t * 1000.0
            if t_ms > duration_ms:
                break
            cap.set(cv2.CAP_PROP_POS_MSEC, t_ms)
            ret, frame = cap.read()
            if ret and frame is not None:
                results.append((float(t), frame))
    finally:
        cap.release()
    return results


# ─── Step 2: Webcam face detection ───────────────────────────────────────────

def _find_webcam_face(
    sampled: list[tuple[float, np.ndarray]],
    detector,
    config: FaceTrackerConfig,
) -> tuple[Optional[FaceDetection], Optional[np.ndarray]]:
    """
    Detect small stable faces across sampled frames — these are webcam overlays.
    Returns (median_FaceDetection, representative_frame) or (None, None).
    """
    # Collect small-face detections: (time_s, FaceDetection, frame)
    entries: list[tuple[float, FaceDetection, np.ndarray]] = []
    for t, frame in sampled:
        dets = detector.detect(frame, config)
        for det in dets:
            if det.face_width < WEBCAM_MAX_FACE_WIDTH_NORM:
                entries.append((t, det, frame))

    if not entries:
        return None, None

    # Find the largest cluster of stable detections (same position across frames)
    best_group: list[tuple[float, FaceDetection, np.ndarray]] = []

    for i, (_, det_i, _) in enumerate(entries):
        group_indices = [i]
        for j, (_, det_j, _) in enumerate(entries):
            if j == i:
                continue
            dist = ((det_i.face_x - det_j.face_x) ** 2 + (det_i.face_y - det_j.face_y) ** 2) ** 0.5
            if dist < WEBCAM_STABILITY_RADIUS_NORM:
                group_indices.append(j)

        # Count distinct timestamps in this group
        unique_times = len({entries[k][0] for k in group_indices})
        if unique_times >= WEBCAM_MIN_FRAME_COUNT and len(group_indices) > len(best_group):
            best_group = [entries[k] for k in group_indices]

    if not best_group:
        return None, None

    # Aggregate the group into a single representative FaceDetection (median values)
    dets_in = [det for _, det, _ in best_group]
    median_det = FaceDetection(
        face_x=statistics.median(d.face_x for d in dets_in),
        face_y=statistics.median(d.face_y for d in dets_in),
        face_width=statistics.median(d.face_width for d in dets_in),
        face_height=statistics.median(d.face_height for d in dets_in),
        confidence=max(d.confidence for d in dets_in),
        person_x=statistics.median(d.person_x for d in dets_in),
        person_y=statistics.median(d.person_y for d in dets_in),
        person_height=statistics.median(d.person_height for d in dets_in),
    )

    # Use the middle frame for Canny (most representative lighting)
    best_frame = best_group[len(best_group) // 2][2]
    return median_det, best_frame


# ─── Step 3: Custom YOLO model for webcam bounds ─────────────────────────────

def find_webcam_bounds_yolo_custom(
    frames: list[np.ndarray],
    src_w: int,
    src_h: int,
    model_path: str = WEBCAM_CUSTOM_MODEL_PATH,
    conf_threshold: float = 0.20,
) -> Optional[tuple[int, int, int, int]]:
    """
    Run prognot-webcam.pt on all sampled frames; return (x, y, w, h) of the
    highest-confidence detection, or None if the model is missing / no detection
    meets conf_threshold (caller falls back to _webcam_bounds_fallback).
    """
    if not os.path.exists(model_path):
        logger.warning("[Gaming] Custom webcam model not found: %s", model_path)
        return None

    try:
        from ultralytics import YOLO
        model = YOLO(model_path)
    except Exception as exc:
        logger.warning("[Gaming] Failed to load custom webcam model: %s", exc)
        return None

    best_conf = 0.0
    best_box: Optional[tuple[int, int, int, int]] = None

    for frame in frames:
        try:
            results = model(frame, verbose=False)
            for r in results:
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    conf = float(box.conf[0])
                    if conf < conf_threshold:
                        continue
                    if conf > best_conf:
                        best_conf = conf
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        best_box = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))
        except Exception as exc:
            logger.warning("[Gaming] Custom YOLO inference error on frame: %s", exc)
            continue

    if best_box is None:
        logger.info("[Gaming] Custom YOLO: no detection above conf=%.2f", conf_threshold)
        return None

    logger.info("[Gaming] Custom YOLO: best_conf=%.3f box=%s", best_conf, best_box)
    return best_box


def _webcam_bounds_fallback(
    face_cx_norm: float,
    face_cy_norm: float,
    face_w_norm: float,
    face_h_norm: float,
    src_w: int,
    src_h: int,
    expand_factor: float = 2.0,
) -> tuple[int, int, int, int]:
    """
    Fallback when Canny finds no rectangle: expand the YOLO face bbox by expand_factor.
    This over-estimates the webcam size, which is safer than under-estimating (bleeding).
    """
    cx = int(face_cx_norm * src_w)
    cy = int(face_cy_norm * src_h)
    fw = int(face_w_norm  * src_w)
    fh = int(face_h_norm  * src_h)
    wc_x = max(0, cx - int(fw * expand_factor / 2))
    wc_y = max(0, cy - int(fh * expand_factor / 2))
    wc_w = min(src_w - wc_x, int(fw * expand_factor))
    wc_h = min(src_h - wc_y, int(fh * expand_factor))
    return wc_x, wc_y, wc_w, wc_h


# ─── Step 3b: Face-anchored webcam crop ──────────────────────────────────────

def _compute_webcam_crop(
    wc_w: int,
    face_cx: int,
    face_cy: int,
    src_w: int,
    src_h: int,
    safety_shave: float = 0.90,
) -> tuple[int, int, int, int]:
    """
    Compute a webcam crop rectangle that:
      1. Takes its WIDTH from the Canny/YOLO detection (× safety_shave to trim edges)
      2. Derives its HEIGHT so the crop matches the 1080×640 panel ratio exactly
         → crop_h = crop_w × (640 / 1080)
      3. Centers the rectangle on the YOLO face center (face_cx, face_cy)
      4. Clamps to source boundaries without resizing

    This guarantees the subsequent `scale=1080:640` is distortion-free because
    the input crop already has the exact 1080:640 aspect ratio.
    Returns (crop_x, crop_y, crop_w, crop_h).
    """
    crop_w = max(1, int(wc_w * safety_shave))
    crop_h = max(1, int(crop_w * WEBCAM_PANEL_H / OUTPUT_W))  # crop_w × (640/1080)

    crop_x = int(face_cx - crop_w / 2)
    crop_y = int(face_cy - crop_h / 2)

    # Clamp: shift back inside frame without resizing
    crop_x = max(0, min(src_w - crop_w, crop_x))
    crop_y = max(0, min(src_h - crop_h, crop_y))

    return crop_x, crop_y, crop_w, crop_h


# ─── Step 4: Game crop calculation ───────────────────────────────────────────

def _overlap_ratio(game_x: float, game_w: int, wc_x: int, wc_w: int) -> float:
    """Fraction of the webcam area that falls inside the proposed game crop window."""
    overlap_px = max(0.0, min(game_x + game_w, float(wc_x + wc_w)) - max(game_x, float(wc_x)))
    return overlap_px / wc_w if wc_w > 0 else 0.0


def _compute_game_crop_x(
    src_w: int,
    game_crop_w: int,
    wc_x: int,
    wc_w: int,
) -> tuple[int, int]:
    """
    Center-first game crop position.

    The crosshair / main action in every game engine is at screen center.
    Start from center and only shift if the webcam overlaps significantly.

    Returns (game_crop_x, game_crop_y). Y is always 0 (full source height).
    """
    center_x = (src_w - game_crop_w) / 2.0
    overlap = _overlap_ratio(center_x, game_crop_w, wc_x, wc_w)

    logger.info(
        "[Gaming] Center crop x=%.0f, webcam=[%d,%d], overlap=%.1f%%",
        center_x, wc_x, wc_x + wc_w, overlap * 100,
    )

    if overlap <= OVERLAP_THRESHOLD:
        # Most webcam overlays are in extreme corners — no shift needed
        return int(round(center_x)), 0

    # Webcam is unusually close to center: shift minimally to clear it
    left_x  = float(wc_x - game_crop_w - EDGE_MARGIN)    # game crop ends before webcam
    right_x = float(wc_x + wc_w + EDGE_MARGIN)           # game crop starts after webcam

    shift_left  = abs(center_x - left_x)
    shift_right = abs(right_x - center_x)

    candidate = left_x if shift_left <= shift_right else right_x
    game_crop_x = int(round(max(0.0, min(float(src_w - game_crop_w), candidate))))

    logger.info(
        "[Gaming] Shifted game crop x=%d (overlap was %.1f%%, left_shift=%.0f right_shift=%.0f)",
        game_crop_x, overlap * 100, shift_left, shift_right,
    )
    return game_crop_x, 0


# ─── Step 5: FFmpeg render ────────────────────────────────────────────────────

def _run_ffmpeg_gaming(
    input_path: str,
    output_path: str,
    wc_x: int, wc_y: int, wc_w: int, wc_h: int,
    game_x: int, game_y: int, game_w: int, game_h: int,
) -> None:
    """
    Render 1080x1920 split-screen video via FFmpeg filter_complex vstack.

    Top panel    (1080x640) : webcam region, letterboxed to preserve aspect ratio
    Bottom panel (1080x1280): gameplay region, scaled to fill
    """
    # Webcam panel: crop is pre-computed at exact 1080:640 ratio (face-anchored),
    # so a simple scale to target dimensions produces zero letterboxing/squashing.
    webcam_filter = (
        f"[0:v]crop={wc_w}:{wc_h}:{wc_x}:{wc_y},"
        f"scale={OUTPUT_W}:{WEBCAM_PANEL_H}"
        "[top]"
    )

    # Game panel: direct scale (crop aspect ratio already matches 1080:1280)
    game_filter = (
        f"[0:v]crop={game_w}:{game_h}:{game_x}:{game_y},"
        f"scale={OUTPUT_W}:{GAME_PANEL_H}"
        "[bottom]"
    )

    filter_complex = f"{webcam_filter};{game_filter};[top][bottom]vstack=inputs=2[out]"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",           # copy audio stream if present
        "-c:v", "libx264",
        "-preset", "fast",        # fast: ~50-100x realtime CPU, crf=18 keeps quality high
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "320k",
        "-movflags", "+faststart",
        output_path,
    ]

    logger.info(
        "[Gaming] FFmpeg: wc=crop(%d:%d:%d:%d)->scale(%dx%d) ratio=%.4f | game=crop(%d:%d:%d:%d)->scale(%dx%d)",
        wc_w, wc_h, wc_x, wc_y, OUTPUT_W, WEBCAM_PANEL_H, wc_w / wc_h if wc_h else 0,
        game_w, game_h, game_x, game_y, OUTPUT_W, GAME_PANEL_H,
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg exited {result.returncode}:\n{result.stderr[-800:]}"
        )

    logger.info("[Gaming] FFmpeg render complete: %s", output_path)


# ─── Step 5b: Debug render (annotated 16:9) ──────────────────────────────────

def _run_ffmpeg_debug(
    input_path: str,
    output_path: str,
    # Raw Canny/YOLO detection bounds (ORANGE) — what the detector returned
    wc_x: int, wc_y: int, wc_w: int, wc_h: int,
    # Face-anchored crop (YELLOW) — what actually gets rendered in the top panel
    cam_x: int, cam_y: int, cam_w: int, cam_h: int,
    game_x: int, game_y: int, game_w: int, game_h: int,
    detected_by: str,
    src_w: int,
    src_h: int,
    overlap_pct: float,
    face_cx: int,
    face_cy: int,
) -> None:
    """
    Render the original 16:9 video with annotated bounding boxes and labels.

    Annotations:
      ORANGE — raw Canny/YOLO detection bounds (what the detector returned)
      YELLOW — face-anchored crop (what actually gets rendered in the top panel)
      RED    — YOLO face center dot (anchor point for crop positioning)
      BLUE   — game crop column (box + semi-transparent fill)
      CYAN   — game center crosshair (output alignment reference)
      WHITE text — coordinates, detection method, overlap %, dimensions, timestamp

    Falls back to boxes-only if drawtext (freetype) is unavailable in the container.
    """
    game_cx = game_x + game_w // 2

    # ── Box annotations (always work, no font required) ───────────────────────
    boxes = [
        # Raw detection: semi-transparent orange fill + dashed border
        f"drawbox=x={wc_x}:y={wc_y}:w={wc_w}:h={wc_h}:color=orange@0.12:t=fill",
        f"drawbox=x={wc_x}:y={wc_y}:w={wc_w}:h={wc_h}:color=orange@1.0:t=3",

        # Face-anchored crop (actual top panel): semi-transparent yellow fill
        f"drawbox=x={cam_x}:y={cam_y}:w={cam_w}:h={cam_h}:color=yellow@0.18:t=fill",
        # Face-anchored crop: solid yellow border (6px)
        f"drawbox=x={cam_x}:y={cam_y}:w={cam_w}:h={cam_h}:color=yellow@1.0:t=6",
        # Crop horizontal center line
        f"drawbox=x={cam_x}:y={face_cy - 1}:w={cam_w}:h=2:color=yellow@0.80:t=fill",
        # Crop vertical center line
        f"drawbox=x={face_cx - 1}:y={cam_y}:w=2:h={cam_h}:color=yellow@0.80:t=fill",

        # Face center: filled red dot (14x14)
        f"drawbox=x={face_cx - 7}:y={face_cy - 7}:w=14:h=14:color=red@1.0:t=fill",
        # Face center: red ring outline (22x22 hollow box, 3px)
        f"drawbox=x={face_cx - 11}:y={face_cy - 11}:w=22:h=22:color=red@1.0:t=3",

        # Game crop: semi-transparent blue fill (full source height column)
        f"drawbox=x={game_x}:y=0:w={game_w}:h={src_h}:color=blue@0.10:t=fill",
        # Game crop: solid blue border (6px, full height)
        f"drawbox=x={game_x}:y=0:w={game_w}:h={src_h}:color=blue@1.0:t=6",
        # Game center: vertical cyan line
        f"drawbox=x={game_cx - 1}:y=0:w=2:h={src_h}:color=cyan@0.75:t=fill",
        # Game center: horizontal cyan line at vertical midpoint
        f"drawbox=x={game_x}:y={src_h // 2 - 1}:w={game_w}:h=2:color=cyan@0.75:t=fill",
        # Game center dot: filled cyan dot (14x14)
        f"drawbox=x={game_cx - 7}:y={src_h // 2 - 7}:w=14:h=14:color=cyan@1.0:t=fill",
    ]

    # ── Text annotations (require libfreetype — may fail on minimal containers) ─
    texts = [
        # Top-left: title
        "drawtext=text='GAMING REFRAME DEBUG':x=12:y=12"
        ":fontcolor=white:fontsize=28:box=1:boxcolor=black@0.75:boxborderw=6",

        # Raw detection label (orange)
        f"drawtext=text='RAW DETECT [{detected_by}]  {wc_w}x{wc_h}  @({wc_x}\\,{wc_y})':"
        f"x={wc_x + 4}:y={max(2, wc_y - 34)}"
        ":fontcolor=orange:fontsize=18:box=1:boxcolor=black@0.75:boxborderw=3",

        # Face-anchored crop label (yellow)
        f"drawtext=text='WEBCAM CROP (face-anchored 90%%)  {cam_w}x{cam_h}  @({cam_x}\\,{cam_y})':"
        f"x={cam_x + 4}:y={cam_y + cam_h + 6}"
        ":fontcolor=yellow:fontsize=18:box=1:boxcolor=black@0.75:boxborderw=3",

        # Face center label (red)
        f"drawtext=text='face @({face_cx}\\,{face_cy})':"
        f"x={face_cx + 16}:y={face_cy - 10}"
        ":fontcolor=red:fontsize=16:box=1:boxcolor=black@0.70:boxborderw=3",

        # Game crop label (top of column)
        f"drawtext=text='GAME CROP  {game_w}x{game_h}  @({game_x}\\,0)':"
        f"x={game_x + 4}:y=50"
        ":fontcolor=cyan:fontsize=20:box=1:boxcolor=black@0.75:boxborderw=4",

        # Info row 1
        f"drawtext=text='overlap={overlap_pct:.1f}%%  src={src_w}x{src_h}':"
        "x=12:y=52"
        ":fontcolor=white:fontsize=18:box=1:boxcolor=black@0.65:boxborderw=3",

        # Info row 2
        f"drawtext=text='output 1080x1920  webcam-panel=1080x{WEBCAM_PANEL_H}  game-panel=1080x{GAME_PANEL_H}':"
        "x=12:y=82"
        ":fontcolor=white:fontsize=16:box=1:boxcolor=black@0.60:boxborderw=3",

        # Timestamp top-right
        "drawtext=text='%{pts\\:hms}':x=(w-tw-12):y=12"
        ":fontcolor=white:fontsize=24:box=1:boxcolor=black@0.75:boxborderw=5",
    ]

    def _build_cmd(vf: str) -> list[str]:
        return [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

    # Try full annotation (boxes + text)
    vf_full = ",".join(boxes + texts)
    result = subprocess.run(_build_cmd(vf_full), capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        # Likely missing freetype/fonts — fall back to boxes only
        logger.warning(
            "[Gaming] drawtext unavailable, retrying with boxes only: %s",
            result.stderr[-200:],
        )
        vf_boxes = ",".join(boxes)
        result = subprocess.run(_build_cmd(vf_boxes), capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg debug render failed (boxes-only fallback): {result.stderr[-600:]}"
            )

    logger.info("[Gaming] Debug render complete: %s", output_path)
