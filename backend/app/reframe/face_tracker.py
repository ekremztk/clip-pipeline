"""
Face Tracker — pluggable detection engine.

Supports two engines (selected at runtime via engine_type param):
  - "mediapipe" (default): BlazeFace model, face-level detection
  - "yolo": YOLOv8-nano, person-level detection with head region estimation

Both engines produce identical FaceDetection output so the rest of the
pipeline (focus_resolver, path_solver, etc.) remains unchanged.

Performance (per-frame ms) is logged for each engine to enable comparison.
"""
import logging
import time
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .config import FaceTrackerConfig
from .types import FaceDetection, Frame, Shot, SHOT_WIDE, SHOT_CLOSEUP, SHOT_BROLL

logger = logging.getLogger(__name__)

# Model paths
_MODELS_DIR = Path(__file__).parent.parent.parent / "models"
_MP_MODEL_FILENAME = "blaze_face_full_range.tflite"
_MP_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/latest/blaze_face_full_range.tflite"


# ─── Abstract base ────────────────────────────────────────────────────────────

class BaseDetector(ABC):
    """Detection engine interface. Both engines implement this."""

    @abstractmethod
    def detect(
        self,
        frame: np.ndarray,
        config: FaceTrackerConfig,
    ) -> list[FaceDetection]:
        """Detect persons/faces in a single BGR frame. Returns FaceDetection list."""

    @property
    @abstractmethod
    def engine_name(self) -> str:
        pass


# ─── MediaPipe engine ─────────────────────────────────────────────────────────

class MediaPipeDetector(BaseDetector):
    """BlazeFace face detection via MediaPipe Tasks API."""

    def __init__(self, config: FaceTrackerConfig):
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        model_path = _MODELS_DIR / _MP_MODEL_FILENAME
        if not model_path.exists():
            logger.info("[FaceTracker] Downloading MediaPipe model...")
            _MODELS_DIR.mkdir(parents=True, exist_ok=True)
            import urllib.request
            urllib.request.urlretrieve(_MP_MODEL_URL, str(model_path))
            logger.info("[FaceTracker] Model downloaded: %s", model_path)

        options = vision.FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.IMAGE,
            min_detection_confidence=config.min_detection_confidence,
        )
        self._detector = vision.FaceDetector.create_from_options(options)
        logger.info("[FaceTracker] MediaPipe FaceDetector initialized (blaze_face_full_range)")

    @property
    def engine_name(self) -> str:
        return "mediapipe"

    def detect(self, frame: np.ndarray, config: FaceTrackerConfig) -> list[FaceDetection]:
        try:
            import mediapipe as mp

            res_w, res_h = config.analysis_resolution
            small = cv2.resize(frame, (res_w, res_h))
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self._detector.detect(mp_image)

            if not result.detections:
                return []

            detections: list[FaceDetection] = []
            for det in result.detections:
                bbox = det.bounding_box
                score = det.categories[0].score if det.categories else 0.0
                if score < config.min_detection_confidence:
                    continue

                fx = (bbox.origin_x + bbox.width / 2) / res_w
                fy = (bbox.origin_y + bbox.height / 2) / res_h
                fw = bbox.width / res_w
                fh = bbox.height / res_h
                fx = max(0.0, min(1.0, fx))
                fy = max(0.0, min(1.0, fy))

                person_h = min(1.0, fh * config.person_height_multiplier)
                person_x = fx
                person_y = min(1.0, fy + person_h * 0.2)

                detections.append(FaceDetection(
                    face_x=round(fx, 5), face_y=round(fy, 5),
                    face_width=round(fw, 5), face_height=round(fh, 5),
                    confidence=round(score, 4),
                    person_x=round(person_x, 5), person_y=round(person_y, 5),
                    person_height=round(person_h, 5),
                ))

            detections.sort(key=lambda d: d.face_width * d.face_height, reverse=True)
            detections = detections[:config.max_faces]
            detections.sort(key=lambda d: d.face_x)
            return detections

        except Exception as e:
            logger.error("[FaceTracker/MediaPipe] Detection error: %s", e)
            return []


# ─── YOLO engine ──────────────────────────────────────────────────────────────

class YoloDetector(BaseDetector):
    """
    YOLOv8-large person detection.

    Detects "person" (class 0) bounding boxes and derives a head anchor
    that is robust to arm extension and posture changes.

    Coordinate conversion:
      person bbox [x1,y1,x2,y2] (normalized) →

      X anchor — shoulder-constrained center:
        Shoulder width ≈ body_h * 0.38 (anatomical ratio, arm-extension-resistant).
        When arms extend beyond this, bbox width grows but the anchor stays
        near the shoulder/head center instead of drifting toward the arm.
        face_x = (x1 + x2) / 2   (bbox center — arms affect both sides
                                   symmetrically or the effect is small)
        face_w = min(body_w, body_h * 0.38)   ← key: shoulder-clamped width

      Y anchor — aspect-ratio-driven head fraction:
        The fraction of bbox height where the head sits varies by posture:
          standing tall  (aspect ~0.25): head at ~8-10% from top
          seated podcast (aspect ~0.45): head at ~18-20% from top
          leaning forward (aspect ~0.60): head at ~23-25% from top
        Formula: fraction = clamp(0.06 + aspect * 0.30, 0.06, 0.28)
        face_y = y1 + body_h * fraction
        face_h = body_h * min(0.35, fraction * 2.5)   (detection window)
    """

    # Shoulder width as a fraction of body bbox height (anthropometric ratio).
    # Arms extending beyond this value don't shift the X anchor.
    SHOULDER_HEIGHT_RATIO = 0.38

    def __init__(self, config: FaceTrackerConfig):
        try:
            from ultralytics import YOLO
        except ImportError:
            raise RuntimeError(
                "ultralytics is not installed. "
                "Run: pip install ultralytics"
            )

        # yolov8l.pt auto-downloads from ultralytics on first use
        self._model = YOLO("yolov8l.pt")

        # Verify which model file was actually loaded (yolov8n ≈ 6MB, yolov8l ≈ 87MB)
        try:
            model_path = self._model.ckpt_path if hasattr(self._model, "ckpt_path") else "unknown"
            model_size_mb = os.path.getsize(str(model_path)) / 1024 / 1024 if model_path != "unknown" and os.path.exists(str(model_path)) else -1
            param_count = sum(p.numel() for p in self._model.model.parameters()) if hasattr(self._model, "model") else -1
            logger.info(
                "[FaceTracker] YOLOv8-large initialized — path=%s size=%.1fMB params=%s",
                model_path, model_size_mb, f"{param_count/1e6:.1f}M" if param_count > 0 else "unknown",
            )
        except Exception as _e:
            logger.info("[FaceTracker] YOLOv8-large initialized (could not verify model details: %s)", _e)

    @property
    def engine_name(self) -> str:
        return "yolo"

    def detect(self, frame: np.ndarray, config: FaceTrackerConfig) -> list[FaceDetection]:
        try:
            # Pass full-resolution frame — YOLO handles internal resize via imgsz.
            # Pre-resizing to analysis_resolution (640x360) before this call was
            # causing detail loss that led to background false positives.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            results = self._model(
                rgb,
                classes=[0],                          # class 0 = person
                imgsz=config.yolo_imgsz,              # 1280px — better accuracy than default 640
                conf=config.min_detection_confidence, # 0.55 — cuts low-confidence background hits
                iou=0.45,                             # NMS threshold — removes overlapping duplicates
                verbose=False,
            )

            if not results or not results[0].boxes:
                return []

            boxes = results[0].boxes
            detections: list[FaceDetection] = []

            for i in range(len(boxes)):
                conf = float(boxes.conf[i])
                if conf < config.min_detection_confidence:
                    continue

                # xyxyn: normalized [x1, y1, x2, y2]
                x1, y1, x2, y2 = [float(v) for v in boxes.xyxyn[i]]
                x1 = max(0.0, min(1.0, x1))
                y1 = max(0.0, min(1.0, y1))
                x2 = max(0.0, min(1.0, x2))
                y2 = max(0.0, min(1.0, y2))

                body_w = x2 - x1
                body_h = y2 - y1

                if body_w <= 0 or body_h <= 0:
                    continue

                # ── X anchor: shoulder-constrained center ─────────────────
                # Shoulder width ≈ 38% of body height regardless of arm extension.
                # Using min(body_w, shoulder_w) as the effective tracking width
                # prevents arm extension from inflating the spread seen by the
                # path solver's motion classifier (Problem 1 fix).
                shoulder_w = body_h * self.SHOULDER_HEIGHT_RATIO
                effective_w = min(body_w, shoulder_w)
                head_cx = (x1 + x2) / 2          # X: full bbox center is best estimate
                head_w = effective_w              # shoulder-clamped width (not arm-inclusive)

                # ── Y anchor: aspect-ratio-driven head fraction ────────────
                # When a person sits (wider bbox → higher aspect ratio), the head
                # sits lower in the bbox than when standing. Fixed 30% breaks here.
                # aspect = w/h: standing ~0.25, seated ~0.45, leaning ~0.60+
                aspect = body_w / body_h
                head_top_fraction = 0.06 + aspect * 0.30
                head_top_fraction = max(0.06, min(0.28, head_top_fraction))
                head_cy = y1 + body_h * head_top_fraction
                head_h = body_h * min(0.35, head_top_fraction * 2.5)

                # Person center (full body — unchanged, used by focus_resolver)
                person_x = head_cx
                person_y = y1 + body_h / 2
                person_h = body_h

                detections.append(FaceDetection(
                    face_x=round(head_cx, 5),
                    face_y=round(head_cy, 5),
                    face_width=round(head_w, 5),
                    face_height=round(head_h, 5),
                    confidence=round(conf, 4),
                    person_x=round(person_x, 5),
                    person_y=round(person_y, 5),
                    person_height=round(person_h, 5),
                ))

            detections.sort(key=lambda d: d.face_width * d.face_height, reverse=True)
            detections = detections[:config.max_faces]
            detections.sort(key=lambda d: d.face_x)
            return detections

        except Exception as e:
            logger.error("[FaceTracker/YOLO] Detection error: %s", e)
            return []


# ─── Factory ──────────────────────────────────────────────────────────────────

_detector_cache: dict[str, BaseDetector] = {}


def _get_detector(engine_type: str, config: FaceTrackerConfig) -> BaseDetector:
    """Lazy-init and cache detector by engine type."""
    if engine_type not in _detector_cache:
        if engine_type == "yolo":
            _detector_cache[engine_type] = YoloDetector(config)
        else:
            _detector_cache[engine_type] = MediaPipeDetector(config)
    return _detector_cache[engine_type]


# ─── Public API ───────────────────────────────────────────────────────────────

def analyze_video(
    video_path: str,
    shots: list[Shot],
    src_w: int,
    src_h: int,
    config: FaceTrackerConfig,
    engine_type: str = "mediapipe",
) -> list[Frame]:
    """
    Sample frames from each shot and detect persons/faces.

    engine_type: "mediapipe" (default) | "yolo"
    Returns list of Frame objects with stable tracking IDs.
    """
    detector = _get_detector(engine_type, config)
    logger.info("[FaceTracker] Engine: %s", detector.engine_name)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("[FaceTracker] Cannot open video: %s", video_path)
        return []

    frames: list[Frame] = []
    prev_faces: list[FaceDetection] = []
    total_ms = 0.0
    frame_count = 0

    try:
        for shot_idx, shot in enumerate(shots):
            sample_times = _get_sample_times(shot, config.sample_fps)

            for t in sample_times:
                raw_frame = _read_frame(cap, t)
                if raw_frame is None:
                    continue

                t0 = time.perf_counter()
                faces = detector.detect(raw_frame, config)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                total_ms += elapsed_ms
                frame_count += 1

                logger.debug(
                    "[FaceTracker/%s] t=%.2fs shot=%d faces=%d %.1fms",
                    detector.engine_name, t, shot_idx, len(faces), elapsed_ms,
                )

                faces = _assign_track_ids(faces, prev_faces)
                frames.append(Frame(time_s=t, shot_index=shot_idx, faces=faces))
                prev_faces = faces

            # Reset tracking at shot boundaries
            prev_faces = []

    finally:
        cap.release()

    avg_ms = total_ms / frame_count if frame_count > 0 else 0.0
    logger.info(
        "[FaceTracker/%s] %d frames analyzed, %d total detections, avg %.1fms/frame",
        detector.engine_name,
        len(frames),
        sum(len(f.faces) for f in frames),
        avg_ms,
    )
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

        face_frame_ratio = (wide + single) / total

        detection_frames = wide + single
        wide_ratio = wide / detection_frames if detection_frames > 0 else 0.0

        if wide_ratio >= 0.20 or wide > total / 2:
            shot.shot_type = SHOT_WIDE
        elif single > total / 2:
            shot.shot_type = SHOT_CLOSEUP
        elif face_frame_ratio >= 0.10:
            shot.shot_type = SHOT_WIDE if wide >= single else SHOT_CLOSEUP
        else:
            shot.shot_type = SHOT_BROLL

        empty = total - wide - single
        logger.info(
            "[FaceTracker] Shot %d (%.1f-%.1fs): %s — %d wide, %d single, %d empty (face_ratio=%.0f%%)",
            shot_idx, shot.start_s, shot.end_s, shot.shot_type, wide, single, empty,
            face_frame_ratio * 100,
        )

    return shots


# ─── Frame sampling ───────────────────────────────────────────────────────────

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


# ─── Tracking ID assignment ───────────────────────────────────────────────────

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

    used_prev: set[int] = set()
    used_curr: set[int] = set()
    pairs: list[tuple[float, int, int]] = []

    for ci, c in enumerate(current):
        for pi, p in enumerate(previous):
            dist = ((c.face_x - p.face_x) ** 2 + (c.face_y - p.face_y) ** 2) ** 0.5
            pairs.append((dist, ci, pi))

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

    next_id = max((p.track_id for p in previous), default=-1) + 1
    for ci, face in enumerate(current):
        if ci not in used_curr:
            face.track_id = next_id
            next_id += 1

    return current
