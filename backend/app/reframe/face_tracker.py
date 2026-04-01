"""
Face Tracker — MediaPipe Tasks API face detection and tracking.

Replaces YOLO frame_analyzer with MediaPipe FaceDetector (Tasks API).
Produces per-frame FaceDetection objects with stable tracking IDs.

Tracking ID assignment uses spatial proximity (center distance)
across consecutive frames — lightweight, no deep re-identification.

Model: blaze_face_short_range.tflite (~224KB, CPU-only, fast)
"""
import logging
import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .config import FaceTrackerConfig
from .types import FaceDetection, Frame, Shot, SHOT_WIDE, SHOT_CLOSEUP, SHOT_BROLL

logger = logging.getLogger(__name__)

# Model path — always relative to backend/models/
_MODELS_DIR = Path(__file__).parent.parent.parent / "models"
_MODEL_FILENAME = "blaze_face_short_range.tflite"
_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"

# Lazy-loaded detector
_detector = None


def _get_detector(config: FaceTrackerConfig):
    """Lazy-init MediaPipe FaceDetector (Tasks API)."""
    global _detector
    if _detector is not None:
        return _detector

    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core.base_options import BaseOptions

    model_path = _MODELS_DIR / _MODEL_FILENAME

    # Auto-download model if missing
    if not model_path.exists():
        logger.info("[FaceTracker] Downloading face detection model...")
        _MODELS_DIR.mkdir(parents=True, exist_ok=True)
        import urllib.request
        urllib.request.urlretrieve(_MODEL_URL, str(model_path))
        logger.info("[FaceTracker] Model downloaded: %s", model_path)

    options = vision.FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.IMAGE,
        min_detection_confidence=config.min_detection_confidence,
    )
    _detector = vision.FaceDetector.create_from_options(options)
    logger.info("[FaceTracker] MediaPipe FaceDetector initialized (blaze_face_short_range)")
    return _detector


def analyze_video(
    video_path: str,
    shots: list[Shot],
    src_w: int,
    src_h: int,
    config: FaceTrackerConfig,
) -> list[Frame]:
    """
    Sample frames from each shot and detect faces using MediaPipe.

    Returns list of Frame objects with stable tracking IDs.
    """
    detector = _get_detector(config)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("[FaceTracker] Cannot open video: %s", video_path)
        return []

    frames: list[Frame] = []
    prev_faces: list[FaceDetection] = []

    try:
        for shot_idx, shot in enumerate(shots):
            sample_times = _get_sample_times(shot, config.sample_fps)

            for t in sample_times:
                raw_frame = _read_frame(cap, t)
                if raw_frame is None:
                    continue

                faces = _detect_faces(detector, raw_frame, config)

                # Assign stable tracking IDs
                faces = _assign_track_ids(faces, prev_faces)

                frames.append(Frame(
                    time_s=t,
                    shot_index=shot_idx,
                    faces=faces,
                ))
                prev_faces = faces

                if faces:
                    logger.debug(
                        "[FaceTracker] t=%.2fs shot=%d faces=%d pos=(%.3f,%.3f)",
                        t, shot_idx, len(faces), faces[0].face_x, faces[0].face_y,
                    )

            # Reset tracking at shot boundaries
            prev_faces = []

    finally:
        cap.release()

    logger.info("[FaceTracker] %d frames analyzed, %d total face detections",
                len(frames), sum(len(f.faces) for f in frames))
    return frames


def classify_shots(
    shots: list[Shot],
    frames: list[Frame],
) -> list[Shot]:
    """
    Classify each shot by face count (majority vote).
    2+ faces → wide, 1 face → closeup, 0 faces → b_roll
    """
    for shot_idx, shot in enumerate(shots):
        counts = [len(f.faces) for f in frames if f.shot_index == shot_idx]

        if not counts:
            shot.shot_type = SHOT_BROLL
            continue

        total = len(counts)
        wide = sum(1 for c in counts if c >= 2)
        single = sum(1 for c in counts if c == 1)
        empty = sum(1 for c in counts if c == 0)

        if wide > total / 2:
            shot.shot_type = SHOT_WIDE
        elif single > total / 2:
            shot.shot_type = SHOT_CLOSEUP
        elif empty > total / 2:
            shot.shot_type = SHOT_BROLL
        elif wide >= single:
            shot.shot_type = SHOT_WIDE
        else:
            shot.shot_type = SHOT_CLOSEUP

        logger.info(
            "[FaceTracker] Shot %d (%.1f-%.1fs): %s — %d wide, %d single, %d empty",
            shot_idx, shot.start_s, shot.end_s, shot.shot_type, wide, single, empty,
        )

    return shots


# --- Frame sampling ----------------------------------------------------------

def _get_sample_times(shot: Shot, sample_fps: float) -> list[float]:
    """Generate sample times within a shot, avoiding edge artifacts."""
    margin = 0.05
    start = shot.start_s + margin
    end = shot.end_s - margin
    if end <= start:
        return [shot.start_s + shot.duration_s / 2]

    interval = 1.0 / sample_fps
    times: list[float] = []
    t = start
    while t < end:
        times.append(round(t, 3))
        t += interval

    if not times:
        times.append(round(start, 3))
    return times


def _read_frame(cap: cv2.VideoCapture, time_s: float) -> Optional[np.ndarray]:
    """Read frame at specific timestamp."""
    cap.set(cv2.CAP_PROP_POS_MSEC, time_s * 1000)
    ret, frame = cap.read()
    return frame if ret else None


# --- MediaPipe detection -----------------------------------------------------

def _detect_faces(
    detector,
    frame: np.ndarray,
    config: FaceTrackerConfig,
) -> list[FaceDetection]:
    """
    Detect faces using MediaPipe Tasks API FaceDetector.
    Returns normalized face positions with estimated person center/height.
    """
    try:
        import mediapipe as mp

        res_w, res_h = config.analysis_resolution
        small = cv2.resize(frame, (res_w, res_h))
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        # MediaPipe Tasks API expects mp.Image
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = detector.detect(mp_image)

        if not result.detections:
            return []

        detections: list[FaceDetection] = []

        for det in result.detections:
            bbox = det.bounding_box
            score = det.categories[0].score if det.categories else 0.0

            if score < config.min_detection_confidence:
                continue

            # bbox: origin_x, origin_y, width, height in pixels (of analysis resolution)
            fx = (bbox.origin_x + bbox.width / 2) / res_w
            fy = (bbox.origin_y + bbox.height / 2) / res_h
            fw = bbox.width / res_w
            fh = bbox.height / res_h

            # Clamp
            fx = max(0.0, min(1.0, fx))
            fy = max(0.0, min(1.0, fy))

            # Estimate person center/height from face
            person_h = min(1.0, fh * config.person_height_multiplier)
            person_x = fx
            person_y = min(1.0, fy + person_h * 0.2)

            detections.append(FaceDetection(
                face_x=round(fx, 5),
                face_y=round(fy, 5),
                face_width=round(fw, 5),
                face_height=round(fh, 5),
                confidence=round(score, 4),
                person_x=round(person_x, 5),
                person_y=round(person_y, 5),
                person_height=round(person_h, 5),
            ))

        # Sort by face size (largest first), keep top N
        detections.sort(key=lambda d: d.face_width * d.face_height, reverse=True)
        detections = detections[:config.max_faces]

        # Sort by X for stable ordering
        detections.sort(key=lambda d: d.face_x)

        return detections

    except Exception as e:
        logger.error("[FaceTracker] Detection error: %s", e)
        return []


# --- Tracking ID assignment --------------------------------------------------

def _assign_track_ids(
    current: list[FaceDetection],
    previous: list[FaceDetection],
) -> list[FaceDetection]:
    """
    Assign stable tracking IDs by spatial proximity to previous frame.
    Resets at shot boundaries (caller passes empty previous list).
    """
    if not previous:
        for i, face in enumerate(current):
            face.track_id = i
        return current

    if not current:
        return current

    # Distance pairs
    used_prev: set[int] = set()
    used_curr: set[int] = set()
    pairs: list[tuple[float, int, int]] = []

    for ci, c in enumerate(current):
        for pi, p in enumerate(previous):
            dist = ((c.face_x - p.face_x) ** 2 + (c.face_y - p.face_y) ** 2) ** 0.5
            pairs.append((dist, ci, pi))

    # Greedy closest match
    pairs.sort(key=lambda p: p[0])
    max_match_dist = 0.15

    for dist, ci, pi in pairs:
        if ci in used_curr or pi in used_prev:
            continue
        if dist > max_match_dist:
            break
        current[ci].track_id = previous[pi].track_id
        used_curr.add(ci)
        used_prev.add(pi)

    # New IDs for unmatched
    next_id = max((p.track_id for p in previous), default=-1) + 1
    for ci, face in enumerate(current):
        if ci not in used_curr:
            face.track_id = next_id
            next_id += 1

    return current
