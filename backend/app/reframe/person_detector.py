"""
Layer 2 — Person Detection
Uses YOLOv8 nano-pose model.
Runs ONLY on the first frame of each scene — not per-frame.
Bounding box coordinates remain constant for the entire scene duration.
This eliminates jitter and drastically reduces CPU load.
"""
import os
import subprocess
import tempfile
from typing import List, Optional

import numpy as np

from app.config import settings
from app.reframe.models.types import Keypoint, PersonDetection, SceneAnalysis, SceneInterval


# ── Filter thresholds ─────────────────────────────────────────────────────────

# Minimum YOLOv8 detection confidence.
# 0.55 rejects shadows, reflections, background monitor faces, and partial
# bodies that nano-pose detects at 0.40–0.54 in podcast environments.
_CONF_THRESHOLD = 0.55

# Minimum bounding box height as fraction of frame height.
# A real person in a podcast shot occupies at least 20% of the frame height.
# Reflections in glass, distant people in backgrounds, or partial body parts
# visible at the frame edge are typically < 0.15.
_MIN_HEIGHT_NORM = 0.20

# Minimum bounding box width as fraction of frame width.
# Catches narrow false positives (e.g. a thin arm or reflection column).
_MIN_WIDTH_NORM  = 0.05

# Reject detections whose center Y is in the bottom 15% of the frame
# (hands on desk, feet, cropped body artefacts).
_MAX_CY_NORM = 0.85

# Reject detections whose center Y is in the top 5% of the frame
# (ceiling fixtures, overhead lights misidentified as people).
_MIN_CY_NORM = 0.05

# Maximum number of persons returned per frame.
# Podcast shoots have at most 2–3 people in frame; anything above that
# is almost certainly noise. We keep the top-N by confidence.
_MAX_PERSONS = 3


# Lazy-loaded global model (loaded once per process)
_yolo_model = None


def _get_model():
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        print(f"[PersonDetector] Loading YOLOv8 model: {settings.YOLOV8_MODEL_PATH}")
        _yolo_model = YOLO(settings.YOLOV8_MODEL_PATH)
        print("[PersonDetector] Model loaded")
    return _yolo_model


def _extract_frame_at(video_path: str, timestamp_s: float) -> Optional[np.ndarray]:
    """
    Extract a single frame at timestamp_s using FFmpeg.
    Returns BGR numpy array or None on failure.
    """
    try:
        import cv2

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()

        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{timestamp_s:.4f}",
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            tmp.name,
        ]
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=True,
        )
        frame = cv2.imread(tmp.name)
        return frame
    except Exception as e:
        print(f"[PersonDetector] Frame extraction failed at {timestamp_s:.3f}s: {e}")
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _keypoints_from_result(kps_xy: np.ndarray, kps_conf: np.ndarray) -> List[Keypoint]:
    """Convert YOLOv8 keypoint arrays to our Keypoint dataclass list."""
    result = []
    for i in range(min(17, len(kps_xy))):
        result.append(Keypoint(
            x_norm=float(kps_xy[i][0]),
            y_norm=float(kps_xy[i][1]),
            confidence=float(kps_conf[i]) if kps_conf is not None and i < len(kps_conf) else 0.0,
        ))
    return result


def _estimate_gaze(keypoints: List[Keypoint], threshold: float = 0.5) -> str:
    """
    Estimate gaze direction from COCO keypoints.
    Uses ear visibility asymmetry as primary signal, eye asymmetry as fallback.

    COCO indices:
      0: nose  1: left_eye  2: right_eye  3: left_ear  4: right_ear
      5: left_shoulder  6: right_shoulder
    """
    if len(keypoints) < 5:
        return "unknown"

    nose_conf       = keypoints[0].confidence
    left_eye_conf   = keypoints[1].confidence
    right_eye_conf  = keypoints[2].confidence
    left_ear_conf   = keypoints[3].confidence
    right_ear_conf  = keypoints[4].confidence

    if nose_conf < threshold:
        return "unknown"

    # Both ears visible → frontal
    if left_ear_conf > threshold and right_ear_conf > threshold:
        return "center"

    # Only right ear visible → person facing their own left (gaze goes right in frame)
    if right_ear_conf > threshold and left_ear_conf < threshold:
        return "right"

    # Only left ear visible → person facing their own right (gaze goes left in frame)
    if left_ear_conf > threshold and right_ear_conf < threshold:
        return "left"

    # Eye asymmetry fallback
    if left_eye_conf > threshold and right_eye_conf < threshold:
        return "right"
    if right_eye_conf > threshold and left_eye_conf < threshold:
        return "left"

    return "center"


def detect_persons_in_frame(frame: np.ndarray) -> List[PersonDetection]:
    """
    Run YOLOv8 pose inference on a single BGR frame.
    Returns up to _MAX_PERSONS PersonDetections, sorted by confidence descending.

    Filter pipeline (each condition rejects the detection):
      1. class != 0 (not a person in COCO)
      2. confidence < _CONF_THRESHOLD (0.55) — eliminates weak false positives
      3. height_norm < _MIN_HEIGHT_NORM (0.20) — eliminates partial bodies / reflections
      4. width_norm < _MIN_WIDTH_NORM (0.05) — eliminates thin column artefacts
      5. cy_norm > _MAX_CY_NORM (0.85) — eliminates bottom-edge body parts
      6. cy_norm < _MIN_CY_NORM (0.05) — eliminates ceiling / overhead artefacts
    """
    if frame is None:
        return []

    model = _get_model()
    h, w = frame.shape[:2]

    try:
        results = model(frame, verbose=False)
    except Exception as e:
        print(f"[PersonDetector] Inference error: {e}")
        return []

    detections: List[PersonDetection] = []

    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue

        keypoints_data = result.keypoints

        for i, box in enumerate(boxes):
            # ── Filter 1: class ──────────────────────────────────────────────
            cls = int(box.cls[0]) if box.cls is not None else -1
            if cls != 0:
                continue

            # ── Filter 2: confidence ─────────────────────────────────────────
            conf = float(box.conf[0]) if box.conf is not None else 0.0
            if conf < _CONF_THRESHOLD:
                continue

            # ── Compute normalized bbox metrics ──────────────────────────────
            xyxy = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = xyxy
            cx_norm     = float((x1 + x2) / 2 / w)
            cy_norm     = float((y1 + y2) / 2 / h)
            width_norm  = float((x2 - x1) / w)
            height_norm = float((y2 - y1) / h)

            # ── Filter 3: too short ──────────────────────────────────────────
            if height_norm < _MIN_HEIGHT_NORM:
                continue

            # ── Filter 4: too narrow ─────────────────────────────────────────
            if width_norm < _MIN_WIDTH_NORM:
                continue

            # ── Filter 5: bottom-edge artefact ──────────────────────────────
            if cy_norm > _MAX_CY_NORM:
                continue

            # ── Filter 6: top-edge artefact ──────────────────────────────────
            if cy_norm < _MIN_CY_NORM:
                continue

            # ── Extract keypoints + gaze ─────────────────────────────────────
            kps_list: Optional[List[Keypoint]] = None
            gaze = "unknown"
            if keypoints_data is not None and i < len(keypoints_data.xy):
                kps_xy   = keypoints_data.xy[i].cpu().numpy()
                kps_conf = keypoints_data.conf[i].cpu().numpy() if keypoints_data.conf is not None else None

                # Normalize keypoints to [0, 1]
                kps_xy_norm = kps_xy.copy()
                kps_xy_norm[:, 0] /= w
                kps_xy_norm[:, 1] /= h

                kps_list = _keypoints_from_result(kps_xy_norm, kps_conf)
                gaze = _estimate_gaze(kps_list)

            detections.append(PersonDetection(
                cx_norm=cx_norm,
                cy_norm=cy_norm,
                width_norm=width_norm,
                height_norm=height_norm,
                confidence=conf,
                gaze_direction=gaze,
                keypoints=kps_list,
            ))

    # Sort by confidence descending, then cap at _MAX_PERSONS
    detections.sort(key=lambda d: d.confidence, reverse=True)
    if len(detections) > _MAX_PERSONS:
        print(
            f"[PersonDetector] {len(detections)} detections after filters — "
            f"capping to top {_MAX_PERSONS} by confidence"
        )
        detections = detections[:_MAX_PERSONS]

    return detections


def build_scene_person_detections(
    video_path: str,
    scenes: List[SceneInterval],
) -> List[SceneAnalysis]:
    """
    For each scene, extract the first frame and run YOLOv8.
    Returns one SceneAnalysis per scene.

    The detection from the first frame is used for the entire scene duration
    — this is intentional to eliminate jitter and reduce CPU usage.
    """
    results: List[SceneAnalysis] = []

    for scene in scenes:
        # Sample slightly past scene start to avoid transition frames.
        # Use 5% of scene duration but cap at 0.3s (long scenes shouldn't
        # wait too far into the scene to detect the right person).
        sample_t = scene.start_s + min(0.3, scene.duration_s * 0.05)
        frame = _extract_frame_at(video_path, sample_t)

        if frame is None:
            print(f"[PersonDetector] No frame at {sample_t:.3f}s, scene [{scene.start_s:.3f}-{scene.end_s:.3f}]")
            results.append(SceneAnalysis(scene=scene, persons=[]))
            continue

        persons = detect_persons_in_frame(frame)
        print(
            f"[PersonDetector] Scene [{scene.start_s:.2f}-{scene.end_s:.2f}s]: "
            f"{len(persons)} person(s)"
            + (f" conf={[f'{p.confidence:.2f}' for p in persons]} "
               f"cx={[f'{p.cx_norm:.2f}' for p in persons]} "
               f"gaze={[p.gaze_direction for p in persons]}" if persons else "")
        )
        results.append(SceneAnalysis(scene=scene, persons=persons))

    return results
