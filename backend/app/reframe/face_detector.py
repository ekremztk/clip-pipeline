"""
Face detection using OpenCV Haar Cascade (CPU-only, no PyTorch/TF).
Detects faces and returns their normalized center-x positions in the frame.
"""

import cv2
import numpy as np
from typing import List, Optional


def _load_cascade(name: str) -> Optional[cv2.CascadeClassifier]:
    path = cv2.data.haarcascades + name
    cc = cv2.CascadeClassifier(path)
    return None if cc.empty() else cc


# Prefer alt2; fall back to default if not available
_DETECTOR: Optional[cv2.CascadeClassifier] = None


def get_detector() -> cv2.CascadeClassifier:
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = _load_cascade("haarcascade_frontalface_alt2.xml")
        if _DETECTOR is None:
            _DETECTOR = _load_cascade("haarcascade_frontalface_default.xml")
        if _DETECTOR is None:
            raise RuntimeError("No Haar cascade face model found in OpenCV data directory")
    return _DETECTOR


# Shared CLAHE instance for contrast enhancement
_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def detect_faces_in_frame(frame: np.ndarray) -> List[dict]:
    """
    Detect faces in a single frame.
    Returns list of dicts: {cx_norm, cy_norm, width_norm, area}
    All positions normalized [0..1] relative to original frame dimensions.
    """
    try:
        orig_h, orig_w = frame.shape[:2]

        # Resize to max 640px wide for consistent, faster detection
        max_w = 640
        scale = min(1.0, max_w / orig_w)
        if scale < 1.0:
            det_w = int(orig_w * scale)
            det_h = int(orig_h * scale)
            small = cv2.resize(frame, (det_w, det_h), interpolation=cv2.INTER_LINEAR)
        else:
            small = frame
            det_w, det_h = orig_w, orig_h

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = _CLAHE.apply(gray)

        detector = get_detector()
        faces = detector.detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(24, 24),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )

        result = []
        if len(faces) == 0:
            return result

        for (x, y, fw, fh) in faces:
            # Normalize relative to detection frame (same proportions as original)
            cx = (x + fw / 2) / det_w
            cy = (y + fh / 2) / det_h
            result.append({
                "cx_norm": float(cx),
                "cy_norm": float(cy),
                "width_norm": float(fw / det_w),
                "area": int(fw * fh),
            })

        # Sort left to right
        result.sort(key=lambda f: f["cx_norm"])
        return result

    except Exception as e:
        print(f"[FaceDetector] Error: {e}")
        return []


def build_scene_face_map(
    video_path: str,
    scene_start_frame: int,
    scene_end_frame: int,
    sample_count: int = 8,
) -> List[float]:
    """
    Sample `sample_count` frames from a scene, detect faces, and build a
    stable face map.

    Returns up to 2 cx_norm values sorted left to right:
      [left_cx]              — single speaker
      [left_cx, right_cx]    — two speakers

    Falls back to [0.5] (center) if no faces detected.
    """
    try:
        cap = cv2.VideoCapture(video_path)
        total_scene_frames = scene_end_frame - scene_start_frame
        if total_scene_frames <= 0:
            cap.release()
            return [0.5]

        step = max(1, total_scene_frames // sample_count)
        sample_frames = [
            scene_start_frame + i * step
            for i in range(sample_count)
            if scene_start_frame + i * step < scene_end_frame
        ]

        all_cx: List[float] = []
        for frame_num in sample_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if not ret:
                continue
            faces = detect_faces_in_frame(frame)
            for f in faces:
                all_cx.append(f["cx_norm"])

        cap.release()

        if not all_cx:
            print(f"[FaceDetector] No faces detected in scene frames {scene_start_frame}-{scene_end_frame}")
            return [0.5]

        print(f"[FaceDetector] Scene {scene_start_frame}-{scene_end_frame}: detected cx={[round(c, 2) for c in all_cx]}")

        # Cluster: left half vs right half of frame
        left_cx = [cx for cx in all_cx if cx <= 0.5]
        right_cx = [cx for cx in all_cx if cx > 0.5]

        face_map: List[float] = []
        if left_cx:
            face_map.append(float(np.median(left_cx)))
        if right_cx:
            face_map.append(float(np.median(right_cx)))

        if not face_map:
            face_map = [float(np.median(all_cx))]

        return face_map

    except Exception as e:
        print(f"[FaceDetector] build_scene_face_map error: {e}")
        return [0.5]
