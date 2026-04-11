"""
Face Tracker — YOLO face detection engine.

Uses YOLOv8-large-face (yolov8l-face.pt) for face-level detection.
Produces FaceDetection output consumed by focus_resolver, path_solver, etc.

Performance (per-frame ms) is logged for monitoring.
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


# Face model paths
_FACE_MODEL_URL = "https://huggingface.co/arnabdhar/YOLOv8-Face-Detection/resolve/main/model.pt"
_FACE_MODEL_BAKED = Path("/root/yolov8l-face.pt")          # pre-downloaded in Modal image
_FACE_MODEL_LOCAL = _MODELS_DIR / "yolov8l-face.pt"        # local fallback / dev


# ─── YOLO face engine ─────────────────────────────────────────────────────────

class YoloDetector(BaseDetector):
    """
    YOLOv8-large face detection (yolov8l-face.pt).

    Uses a face-specific model that outputs face bounding boxes directly
    (class 0 = face). No body→head estimation math needed.

    The green debug rectangle is now face-sized, and focus points track
    actual face centers — correct for podcast / talk-show content.
    """

    def __init__(self, config: FaceTrackerConfig):
        try:
            from ultralytics import YOLO
        except ImportError:
            raise RuntimeError("ultralytics is not installed. Run: pip install ultralytics")

        # Resolve model: Modal pre-baked path → local models dir → download
        model_path: Optional[Path] = None
        for candidate in [_FACE_MODEL_BAKED, _FACE_MODEL_LOCAL]:
            if candidate.exists():
                model_path = candidate
                break

        if model_path is None:
            logger.info("[FaceTracker] Downloading yolov8l-face.pt from HuggingFace...")
            _FACE_MODEL_LOCAL.parent.mkdir(parents=True, exist_ok=True)
            import requests as _req
            r = _req.get(_FACE_MODEL_URL, stream=True, timeout=300)
            r.raise_for_status()
            with open(str(_FACE_MODEL_LOCAL), "wb") as f:
                f.write(r.content)
            model_path = _FACE_MODEL_LOCAL

        self._model = YOLO(str(model_path))

        try:
            size_mb = os.path.getsize(str(model_path)) / 1024 / 1024
            param_count = sum(p.numel() for p in self._model.model.parameters()) if hasattr(self._model, "model") else -1
            logger.info(
                "[FaceTracker] YOLOv8-large-face initialized — path=%s size=%.1fMB params=%s",
                model_path, size_mb, f"{param_count/1e6:.1f}M" if param_count > 0 else "unknown",
            )
        except Exception as _e:
            logger.info("[FaceTracker] YOLOv8-large-face initialized (could not verify: %s)", _e)

    @property
    def engine_name(self) -> str:
        return "yolo-face"

    def detect(self, frame: np.ndarray, config: FaceTrackerConfig) -> list[FaceDetection]:
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Face model: class 0 = face bbox directly. No class filtering needed.
            results = self._model(
                rgb,
                imgsz=config.yolo_imgsz,
                conf=config.min_detection_confidence,
                iou=0.45,
                verbose=False,
            )

            if not results or not results[0].boxes:
                return []

            boxes = results[0].boxes
            detections: list[FaceDetection] = []

            for i in range(len(boxes)):
                conf = float(boxes.conf[i])

                # xyxyn: normalized [x1, y1, x2, y2] — face bounding box directly
                x1, y1, x2, y2 = [float(v) for v in boxes.xyxyn[i]]
                x1 = max(0.0, min(1.0, x1))
                y1 = max(0.0, min(1.0, y1))
                x2 = max(0.0, min(1.0, x2))
                y2 = max(0.0, min(1.0, y2))

                face_w = x2 - x1
                face_h = y2 - y1

                if face_w <= 0 or face_h <= 0:
                    continue

                face_cx = (x1 + x2) / 2
                face_cy = (y1 + y2) / 2

                # Estimate body position from face (used by focus_resolver)
                person_h = min(1.0, face_h * config.person_height_multiplier)
                person_x = face_cx
                person_y = min(1.0, face_cy + person_h * 0.2)

                detections.append(FaceDetection(
                    face_x=round(face_cx, 5),
                    face_y=round(face_cy, 5),
                    face_width=round(face_w, 5),
                    face_height=round(face_h, 5),
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
            logger.error("[FaceTracker/YOLO-face] Detection error: %s", e)
            return []


# ─── Factory ──────────────────────────────────────────────────────────────────

_detector_cache: dict[str, BaseDetector] = {}


def _get_detector(engine_type: str, config: FaceTrackerConfig) -> BaseDetector:
    """Lazy-init and cache the YOLO face detector."""
    if "yolo" not in _detector_cache:
        _detector_cache["yolo"] = YoloDetector(config)
    return _detector_cache["yolo"]


# ─── Public API ───────────────────────────────────────────────────────────────

def analyze_video(
    video_path: str,
    shots: list[Shot],
    src_w: int,
    src_h: int,
    config: FaceTrackerConfig,
    engine_type: str = "yolo",
) -> list[Frame]:
    """
    Sample frames from each shot and detect faces via YOLO.
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
