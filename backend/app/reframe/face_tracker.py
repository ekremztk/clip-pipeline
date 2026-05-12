"""
Face Tracker — selectable face detection engines.

Uses YOLO-family face detectors for face-level detection.
Produces FaceDetection output consumed by focus_resolver, path_solver, etc.

Performance (per-frame ms) is logged for monitoring.
"""
import os
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
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


# Face model profiles
_FACE_MODEL_LEGACY_URL = "https://huggingface.co/arnabdhar/YOLOv8-Face-Detection/resolve/main/model.pt"

@dataclass(frozen=True)
class DetectorProfile:
    key: str
    display_name: str
    filename: str
    url: str
    baked_paths: tuple[Path, ...]
    class_names: tuple[str, ...] = ()
    iou: float = 0.45


_DETECTOR_PROFILES: dict[str, DetectorProfile] = {
    "yolo-face-large": DetectorProfile(
        key="yolo-face-large",
        display_name="YOLOv8 face large",
        filename="yolov8l-face.pt",
        url=_FACE_MODEL_LEGACY_URL,
        baked_paths=(
            Path("/root/yolov8l-face.pt"),
            Path("/app/models/yolov8l-face.pt"),
            _MODELS_DIR / "yolov8l-face.pt",
        ),
    ),
}

_DETECTOR_ALIASES = {
    "yolo": "yolo-face-large",
    "yolo-face": "yolo-face-large",
    "yolo-face-large": "yolo-face-large",
    "insightface": "insightface-scrfd",
    "insight-face": "insightface-scrfd",
    "scrfd": "insightface-scrfd",
    "insightface-scrfd": "insightface-scrfd",
}


# ─── YOLO face engine ─────────────────────────────────────────────────────────

class YoloDetector(BaseDetector):
    """
    YOLO face detection using a detector profile.

    Profiles can be swapped without changing focus resolver or renderer code.
    """

    def __init__(self, profile: DetectorProfile, config: FaceTrackerConfig):
        try:
            from ultralytics import YOLO
        except ImportError:
            raise RuntimeError("ultralytics is not installed. Run: pip install ultralytics")

        self.profile = profile

        # Resolve model: Modal pre-baked path -> local models dir -> download
        model_path: Optional[Path] = None
        for candidate in profile.baked_paths:
            if candidate.exists():
                model_path = candidate
                break

        if model_path is None:
            model_path = _MODELS_DIR / profile.filename
            logger.info("[FaceTracker] Downloading %s from HuggingFace...", profile.filename)
            model_path.parent.mkdir(parents=True, exist_ok=True)
            import requests as _req
            r = _req.get(profile.url, stream=True, timeout=300)
            r.raise_for_status()
            with open(str(model_path), "wb") as f:
                f.write(r.content)

        self._model = YOLO(str(model_path))

        try:
            size_mb = os.path.getsize(str(model_path)) / 1024 / 1024
            param_count = sum(p.numel() for p in self._model.model.parameters()) if hasattr(self._model, "model") else -1
            logger.info(
                "[FaceTracker] %s initialized — key=%s path=%s size=%.1fMB params=%s classes=%s",
                profile.display_name,
                profile.key,
                model_path,
                size_mb,
                f"{param_count/1e6:.1f}M" if param_count > 0 else "unknown",
                ",".join(profile.class_names) if profile.class_names else "all",
            )
        except Exception as _e:
            logger.info("[FaceTracker] %s initialized (could not verify: %s)", profile.display_name, _e)

    @property
    def engine_name(self) -> str:
        return self.profile.key

    def detect(self, frame: np.ndarray, config: FaceTrackerConfig) -> list[FaceDetection]:
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            results = self._model(
                rgb,
                imgsz=config.yolo_imgsz,
                conf=config.min_detection_confidence,
                iou=self.profile.iou,
                verbose=False,
            )

            if not results or not results[0].boxes:
                return []

            boxes = results[0].boxes
            detections: list[FaceDetection] = []

            for i in range(len(boxes)):
                if not self._is_face_box(results[0], boxes, i):
                    continue

                conf = float(boxes.conf[i])

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
            logger.error("[FaceTracker/%s] Detection error: %s", self.engine_name, e)
            return []

    def _is_face_box(self, result, boxes, index: int) -> bool:
        if not self.profile.class_names:
            return True

        try:
            cls_id = int(boxes.cls[index])
            names = getattr(result, "names", {}) or {}
            class_name = str(names.get(cls_id, cls_id)).lower().strip()
            return class_name in self.profile.class_names
        except Exception:
            return True


class InsightFaceScrfdDetector(BaseDetector):
    """
    InsightFace FaceAnalysis detector using SCRFD from the buffalo_l model pack.

    Only detection is enabled; recognition/embedding modules are not loaded.
    """

    def __init__(self, config: FaceTrackerConfig):
        try:
            import onnxruntime as ort
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise RuntimeError(
                "InsightFace detector requires insightface and onnxruntime-gpu in the Modal image"
            ) from exc

        available_providers = set(ort.get_available_providers())
        providers = [
            provider
            for provider in ("CUDAExecutionProvider", "CPUExecutionProvider")
            if provider in available_providers
        ]
        if not providers:
            providers = ["CPUExecutionProvider"]

        self._providers = providers
        self._ctx_id = 0 if "CUDAExecutionProvider" in providers else -1
        self._app = FaceAnalysis(
            name="buffalo_l",
            allowed_modules=["detection"],
            providers=providers,
        )
        det_size = (config.yolo_imgsz, config.yolo_imgsz)
        self._app.prepare(
            ctx_id=self._ctx_id,
            det_thresh=config.min_detection_confidence,
            det_size=det_size,
        )
        logger.info(
            "[FaceTracker] InsightFace SCRFD initialized - providers=%s det_size=%s ctx_id=%s",
            ",".join(providers),
            det_size,
            self._ctx_id,
        )

    @property
    def engine_name(self) -> str:
        return "insightface-scrfd"

    def detect(self, frame: np.ndarray, config: FaceTrackerConfig) -> list[FaceDetection]:
        try:
            src_h, src_w = frame.shape[:2]
            faces = self._app.get(frame, max_num=config.max_faces)
            detections: list[FaceDetection] = []

            for face in faces:
                x1, y1, x2, y2 = [float(v) for v in face.bbox[:4]]
                x1 = _clamp(x1 / src_w, 0.0, 1.0)
                y1 = _clamp(y1 / src_h, 0.0, 1.0)
                x2 = _clamp(x2 / src_w, 0.0, 1.0)
                y2 = _clamp(y2 / src_h, 0.0, 1.0)

                face_w = x2 - x1
                face_h = y2 - y1
                if face_w <= 0 or face_h <= 0:
                    continue

                face_cx = (x1 + x2) / 2
                face_cy = (y1 + y2) / 2
                person_h = min(1.0, face_h * config.person_height_multiplier)
                person_x = face_cx
                person_y = min(1.0, face_cy + person_h * 0.2)
                confidence = float(getattr(face, "det_score", 0.0))

                detections.append(FaceDetection(
                    face_x=round(face_cx, 5),
                    face_y=round(face_cy, 5),
                    face_width=round(face_w, 5),
                    face_height=round(face_h, 5),
                    confidence=round(confidence, 4),
                    person_x=round(person_x, 5),
                    person_y=round(person_y, 5),
                    person_height=round(person_h, 5),
                ))

            detections.sort(key=lambda d: d.face_width * d.face_height, reverse=True)
            detections = detections[:config.max_faces]
            detections.sort(key=lambda d: d.face_x)
            return detections

        except Exception as e:
            logger.error("[FaceTracker/%s] Detection error: %s", self.engine_name, e)
            return []


# ─── Factory ──────────────────────────────────────────────────────────────────

_detector_cache: dict[str, BaseDetector] = {}
_detector_lock = threading.Lock()


def available_detection_engines() -> list[str]:
    return sorted([*_DETECTOR_PROFILES, "insightface-scrfd"])


def normalize_detection_engine(value: Optional[str]) -> str:
    raw = (value or "yolo").strip().lower().replace("_", "-")
    if not raw:
        raw = "yolo"
    normalized = _DETECTOR_ALIASES.get(raw)
    if not normalized:
        raise ValueError(
            f"Unknown detection engine '{value}'. Available: {', '.join(available_detection_engines())}"
        )
    return normalized


def parse_detection_engine_spec(value: Optional[str]) -> tuple[str, list[str]]:
    """
    Parse a detector spec.

    Examples:
        yolo
        insightface
        compare:yolo,insightface
    """
    raw = (value or "yolo").strip()
    if raw.lower().startswith("compare:"):
        items = [
            normalize_detection_engine(item)
            for item in raw.split(":", 1)[1].split(",")
            if item.strip()
        ]
        engines = _dedupe_preserve_order(items)
        if len(engines) < 2:
            raise ValueError("Detector compare mode requires at least two engines")
        return "compare", engines

    return "single", [normalize_detection_engine(raw)]


def _get_detector(engine_type: str, config: FaceTrackerConfig) -> BaseDetector:
    """Lazy-init and cache detectors by normalized engine key."""
    engine_key = normalize_detection_engine(engine_type)
    if engine_key not in _detector_cache:
        with _detector_lock:
            if engine_key not in _detector_cache:
                if engine_key == "insightface-scrfd":
                    _detector_cache[engine_key] = InsightFaceScrfdDetector(config)
                else:
                    _detector_cache[engine_key] = YoloDetector(_DETECTOR_PROFILES[engine_key], config)
    return _detector_cache[engine_key]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


# ─── Persistent tracklet memory ───────────────────────────────────────────────

@dataclass
class _TrackState:
    track_id: int
    last_x: float
    last_y: float
    last_w: float
    last_h: float
    last_seen_s: float
    vx: float = 0.0
    vy: float = 0.0
    seen_count: int = 1

    def predict(self, time_s: float) -> tuple[float, float]:
        dt = max(0.0, time_s - self.last_seen_s)
        x = max(0.0, min(1.0, self.last_x + self.vx * dt))
        y = max(0.0, min(1.0, self.last_y + self.vy * dt))
        return x, y


class _TrackMemory:
    """Per-shot track memory that survives short detector dropouts."""

    def __init__(self, config: FaceTrackerConfig):
        self.config = config
        self.tracks: dict[int, _TrackState] = {}
        self.next_id = 0
        self.recovered_count = 0
        self.new_count = 0

    def assign(self, faces: list[FaceDetection], time_s: float) -> list[FaceDetection]:
        self._prune(time_s)

        if not faces:
            return faces

        used_faces: set[int] = set()
        used_tracks: set[int] = set()
        pairs: list[tuple[float, int, int, float]] = []

        for face_idx, face in enumerate(faces):
            for track_id, track in self.tracks.items():
                gap_s = max(0.0, time_s - track.last_seen_s)
                max_dist = min(
                    self.config.track_match_max_dist,
                    self.config.track_match_base_dist
                    + gap_s * self.config.track_match_growth_per_s,
                )
                dist = _distance_to_track(face, track, time_s)
                if dist > max_dist:
                    continue

                size_delta = _relative_size_delta(face, track)
                cost = dist + self.config.track_size_weight * size_delta
                pairs.append((cost, face_idx, track_id, gap_s))

        pairs.sort(key=lambda item: item[0])

        for _cost, face_idx, track_id, gap_s in pairs:
            if face_idx in used_faces or track_id in used_tracks:
                continue
            face = faces[face_idx]
            track = self.tracks[track_id]
            self._update_track(track, face, time_s)
            face.track_id = track_id
            face.track_age = track.seen_count
            face.track_gap_s = round(gap_s, 3)
            used_faces.add(face_idx)
            used_tracks.add(track_id)
            if gap_s > (1.5 / max(self.config.sample_fps, 0.1)):
                self.recovered_count += 1
                logger.info(
                    "[FaceTracker] Recovered track_id=%d after %.2fs gap at t=%.2fs",
                    track_id, gap_s, time_s,
                )

        for face_idx, face in enumerate(faces):
            if face_idx in used_faces:
                continue
            track_id = self.next_id
            self.next_id += 1
            self.tracks[track_id] = _TrackState(
                track_id=track_id,
                last_x=face.face_x,
                last_y=face.face_y,
                last_w=face.face_width,
                last_h=face.face_height,
                last_seen_s=time_s,
            )
            face.track_id = track_id
            face.track_age = 1
            face.track_gap_s = 0.0
            self.new_count += 1

        return faces

    def _update_track(
        self,
        track: _TrackState,
        face: FaceDetection,
        time_s: float,
    ) -> None:
        dt = max(0.001, time_s - track.last_seen_s)
        measured_vx = (face.face_x - track.last_x) / dt
        measured_vy = (face.face_y - track.last_y) / dt
        track.vx = _clamp(0.65 * track.vx + 0.35 * measured_vx, -1.0, 1.0)
        track.vy = _clamp(0.65 * track.vy + 0.35 * measured_vy, -1.0, 1.0)
        track.last_x = face.face_x
        track.last_y = face.face_y
        track.last_w = face.face_width
        track.last_h = face.face_height
        track.last_seen_s = time_s
        track.seen_count += 1

    def _prune(self, time_s: float) -> None:
        expired = [
            track_id
            for track_id, track in self.tracks.items()
            if time_s - track.last_seen_s > self.config.track_lost_ttl_s
        ]
        for track_id in expired:
            del self.tracks[track_id]


def _distance_to_track(face: FaceDetection, track: _TrackState, time_s: float) -> float:
    pred_x, pred_y = track.predict(time_s)
    return ((face.face_x - pred_x) ** 2 + (face.face_y - pred_y) ** 2) ** 0.5


def _relative_size_delta(face: FaceDetection, track: _TrackState) -> float:
    prev_area = max(track.last_w * track.last_h, 0.0001)
    curr_area = max(face.face_width * face.face_height, 0.0001)
    return abs(curr_area - prev_area) / max(curr_area, prev_area)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


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
    total_ms = 0.0
    frame_count = 0
    recovered_tracks_total = 0
    new_tracks_total = 0

    try:
        for shot_idx, shot in enumerate(shots):
            sample_times = _get_sample_times(shot, config.sample_fps)
            track_memory = _TrackMemory(config)

            # Per-shot track_id stability tracking
            shot_track_positions: dict[int, list[tuple[float, float]]] = {}

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

                faces = track_memory.assign(faces, t)
                frames.append(Frame(time_s=t, shot_index=shot_idx, faces=faces))

                for f in faces:
                    shot_track_positions.setdefault(f.track_id, []).append((f.face_x, f.face_y))

            recovered_tracks_total += track_memory.recovered_count
            new_tracks_total += track_memory.new_count

            # Log per-shot track_id stability diagnostics
            if shot_track_positions:
                for tid, positions in sorted(shot_track_positions.items()):
                    if len(positions) < 2:
                        continue
                    xs = [p[0] for p in positions]
                    x_spread = max(xs) - min(xs)
                    avg_x = sum(xs) / len(xs)
                    logger.info(
                        "[FaceTracker] Shot %d track_id=%d: %d frames, avg_x=%.3f, x_spread=%.3f%s",
                        shot_idx, tid, len(positions), avg_x, x_spread,
                        " ⚠️UNSTABLE" if x_spread > 0.15 else "",
                    )

    finally:
        cap.release()

    avg_ms = total_ms / frame_count if frame_count > 0 else 0.0
    logger.info(
        "[FaceTracker/%s] %d frames analyzed, %d detections, %d new tracks, %d recovered tracks, avg %.1fms/frame",
        detector.engine_name,
        len(frames),
        sum(len(f.faces) for f in frames),
        new_tracks_total,
        recovered_tracks_total,
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
