"""
Face detection using OpenCV Haar Cascade (CPU-only, no PyTorch/TF).
Detects faces and returns their normalized center-x positions in the frame.
"""

import cv2
import numpy as np
from typing import List, Optional


def _get_detector():
    """Load Haar Cascade face detector (bundled with opencv-python-headless)."""
    path = cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"
    detector = cv2.CascadeClassifier(path)
    if detector.empty():
        raise RuntimeError("Failed to load haarcascade_frontalface_alt2.xml")
    return detector


_DETECTOR = None


def get_detector():
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = _get_detector()
    return _DETECTOR


def detect_faces_in_frame(frame: np.ndarray) -> List[dict]:
    """
    Detect faces in a single frame.
    Returns list of dicts: {cx_norm: float, cy_norm: float, width_norm: float, area: int}
    cx_norm and cy_norm are normalized [0..1] relative to frame dimensions.
    """
    try:
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detector = get_detector()

        faces = detector.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(max(30, w // 20), max(30, h // 20)),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )

        result = []
        if len(faces) == 0:
            return result

        for (x, y, fw, fh) in faces:
            cx = (x + fw / 2) / w
            cy = (y + fh / 2) / h
            result.append({
                "cx_norm": float(cx),
                "cy_norm": float(cy),
                "width_norm": float(fw / w),
                "area": int(fw * fh),
            })

        # Sort left to right by cx_norm
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
) -> List[Optional[float]]:
    """
    Sample `sample_count` frames from a scene, detect faces, and build a
    stable face map for that scene.

    Returns a list of up to 2 x-positions (normalized), sorted left to right.
    Index 0 = left speaker (Speaker 0 / Host)
    Index 1 = right speaker (Speaker 1 / Guest)

    If only one face is found, returns [cx_norm].
    If no faces, returns [0.5] (center fallback).
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

        # Collect all detected cx_norm positions across samples
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
            return [0.5]

        # Cluster cx values: faces on the left half vs right half
        left_cx = [cx for cx in all_cx if cx <= 0.5]
        right_cx = [cx for cx in all_cx if cx > 0.5]

        face_map = []
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
