"""
Face detection using OpenCV Haar Cascade (CPU-only, no PyTorch/TF).

Builds per-frame face position arrays by sampling the video at regular
intervals, filtering false positives, and interpolating between samples.
"""

import cv2
import numpy as np
from typing import Dict, Tuple

_DETECTOR = None
_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def get_detector() -> cv2.CascadeClassifier:
    global _DETECTOR
    if _DETECTOR is None:
        for name in ["haarcascade_frontalface_alt2.xml", "haarcascade_frontalface_default.xml"]:
            cc = cv2.CascadeClassifier(cv2.data.haarcascades + name)
            if not cc.empty():
                _DETECTOR = cc
                print(f"[FaceDetector] Loaded {name}")
                break
        if _DETECTOR is None:
            raise RuntimeError("No Haar cascade face model found in OpenCV data directory")
    return _DETECTOR


def detect_faces_in_frame(frame: np.ndarray) -> list:
    """
    Detect faces in a single frame.

    Returns list of {cx_norm, cy_norm, width_norm, area} sorted by area (largest first).
    Faces in the lower 15% of the frame are discarded (hands, objects, reflections).
    """
    try:
        orig_h, orig_w = frame.shape[:2]

        # Resize to max 640px wide — faster and consistent detection scale
        scale = min(1.0, 640 / orig_w)
        if scale < 1.0:
            dw = int(orig_w * scale)
            dh = int(orig_h * scale)
            small = cv2.resize(frame, (dw, dh), interpolation=cv2.INTER_LINEAR)
        else:
            small, dw, dh = frame, orig_w, orig_h

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = _CLAHE.apply(gray)

        raw = get_detector().detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(24, 24),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )

        if len(raw) == 0:
            return []

        result = []
        for (x, y, fw, fh) in raw:
            cx = (x + fw / 2) / dw
            cy = (y + fh / 2) / dh
            # Reject faces in lower 15% — these are almost always false positives
            # (hands raised, shoulders, reflections)
            if cy > 0.85:
                continue
            result.append({
                "cx_norm": float(cx),
                "cy_norm": float(cy),
                "width_norm": float(fw / dw),
                "area": int(fw * fh),
            })

        # Largest faces first (most likely to be the actual person)
        result.sort(key=lambda f: f["area"], reverse=True)
        return result

    except Exception as e:
        print(f"[FaceDetector] detect_faces_in_frame error: {e}")
        return []


def build_video_face_positions(
    video_path: str,
    total_frames: int,
    fps: float,
    sample_interval_s: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build per-frame face position arrays by sampling the video at regular intervals.

    Sampling strategy:
    - Sample every `sample_interval_s` seconds (default 0.5s)
    - For each sample: detect faces, assign to left (cx ≤ 0.5) or right (cx > 0.5) side
    - Remove outlier detections (sudden large jumps — likely false positives)
    - Linearly interpolate between valid samples to fill all frames

    Returns:
      left_cx  — np.ndarray[float32] of length total_frames, NaN = no face on left
      right_cx — np.ndarray[float32] of length total_frames, NaN = no face on right

    Convention:
      left side  → Speaker 0 / HOST
      right side → Speaker 1 / GUEST
    """
    try:
        sample_step = max(1, int(sample_interval_s * fps))
        sample_frames = list(range(0, total_frames, sample_step))

        raw_left: Dict[int, float] = {}
        raw_right: Dict[int, float] = {}

        cap = cv2.VideoCapture(video_path)
        detected_count = 0

        for fn in sample_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
            ret, frame = cap.read()
            if not ret:
                continue

            faces = detect_faces_in_frame(frame)
            if not faces:
                continue

            detected_count += 1
            left_faces = [f for f in faces if f["cx_norm"] <= 0.5]
            right_faces = [f for f in faces if f["cx_norm"] > 0.5]

            # Take the largest face on each side
            if left_faces:
                raw_left[fn] = left_faces[0]["cx_norm"]
            if right_faces:
                raw_right[fn] = right_faces[0]["cx_norm"]

        cap.release()
        print(f"[FaceDetector] {detected_count}/{len(sample_frames)} samples had faces "
              f"(left: {len(raw_left)}, right: {len(raw_right)})")

        left_cx = _build_interpolated_array(raw_left, total_frames)
        right_cx = _build_interpolated_array(raw_right, total_frames)

        return left_cx, right_cx

    except Exception as e:
        print(f"[FaceDetector] build_video_face_positions error: {e}")
        nan = np.full(total_frames, np.nan, dtype=np.float32)
        return nan.copy(), nan.copy()


def _build_interpolated_array(raw: Dict[int, float], total_frames: int) -> np.ndarray:
    """
    Convert sparse {frame_num: cx_norm} detections to a per-frame interpolated array.

    Steps:
    1. Remove outliers: detection that differs from both adjacent detections by > 0.3
       is almost certainly a false positive (e.g., hand moving into frame)
    2. Write cleaned values into array
    3. Linearly interpolate between valid points
       (np.interp also extrapolates at edges, holding first/last value)
    """
    arr = np.full(total_frames, np.nan, dtype=np.float32)

    if not raw:
        return arr

    keys = sorted(raw.keys())
    vals = [raw[k] for k in keys]

    # Step 1 — outlier removal
    clean_keys = []
    clean_vals = []
    for i, (k, v) in enumerate(zip(keys, vals)):
        neighbors = []
        if i > 0:
            neighbors.append(vals[i - 1])
        if i < len(vals) - 1:
            neighbors.append(vals[i + 1])

        if neighbors and abs(v - float(np.median(neighbors))) > 0.30:
            continue  # False positive: skip

        clean_keys.append(k)
        clean_vals.append(v)

    if not clean_keys:
        return arr

    # Step 2 — write cleaned values
    for k, v in zip(clean_keys, clean_vals):
        arr[k] = v

    # Step 3 — interpolate
    valid = np.where(~np.isnan(arr))[0]
    if len(valid) >= 2:
        arr[:] = np.interp(np.arange(total_frames), valid, arr[valid]).astype(np.float32)
    elif len(valid) == 1:
        arr[:] = arr[valid[0]]

    return arr
