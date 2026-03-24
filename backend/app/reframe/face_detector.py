"""
Face detection using OpenCV DNN — ResNet-10 SSD (CPU-only, no PyTorch/TF).
Falls back to Haar Cascade if model download fails.

The DNN model is ~10 MB and is downloaded once to the models/ directory.
It provides confidence scores and works at various face angles, unlike
Haar Cascade which only reliably detects frontal faces.
"""

import os
import cv2
import numpy as np
import urllib.request
from typing import Dict, List, Tuple, Optional

# ── DNN Model Files ───────────────────────────────────────────────────────────

_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
_PROTOTXT_PATH = os.path.join(_MODEL_DIR, "deploy.prototxt")
_CAFFEMODEL_PATH = os.path.join(_MODEL_DIR, "face_detector.caffemodel")

_PROTOTXT_URL = (
    "https://raw.githubusercontent.com/opencv/opencv/master"
    "/samples/dnn/face_detector/deploy.prototxt"
)
_CAFFEMODEL_URL = (
    "https://github.com/opencv/opencv_3rdparty/raw"
    "/dnn_samples_face_detector_20170830"
    "/res10_300x300_ssd_iter_140000.caffemodel"
)

# Global state — initialized once per process
_dnn_net: Optional[cv2.dnn_Net] = None
_use_dnn: Optional[bool] = None  # None = not yet tried
_haar: Optional[cv2.CascadeClassifier] = None
_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


# ── Initialization ────────────────────────────────────────────────────────────

def _init_dnn() -> bool:
    """Download and load the DNN model. Returns True on success."""
    global _dnn_net
    try:
        os.makedirs(_MODEL_DIR, exist_ok=True)

        if not os.path.exists(_PROTOTXT_PATH):
            print("[FaceDetector] Downloading deploy.prototxt …")
            urllib.request.urlretrieve(_PROTOTXT_URL, _PROTOTXT_PATH)

        if not os.path.exists(_CAFFEMODEL_PATH):
            print("[FaceDetector] Downloading face detector model (~10 MB) …")
            urllib.request.urlretrieve(_CAFFEMODEL_URL, _CAFFEMODEL_PATH)

        _dnn_net = cv2.dnn.readNetFromCaffe(_PROTOTXT_PATH, _CAFFEMODEL_PATH)
        print("[FaceDetector] DNN model loaded ✓")
        return True

    except Exception as e:
        print(f"[FaceDetector] DNN init failed ({e}) — falling back to Haar Cascade")
        return False


def _ensure_ready():
    global _use_dnn
    if _use_dnn is None:
        _use_dnn = _init_dnn()


def _get_haar() -> Optional[cv2.CascadeClassifier]:
    global _haar
    if _haar is None:
        for name in ["haarcascade_frontalface_alt2.xml", "haarcascade_frontalface_default.xml"]:
            cc = cv2.CascadeClassifier(cv2.data.haarcascades + name)
            if not cc.empty():
                _haar = cc
                break
    return _haar


# ── Single-Frame Detection ────────────────────────────────────────────────────

def detect_faces_in_frame(frame: np.ndarray) -> List[dict]:
    """
    Detect faces in a single BGR frame.

    Returns list of {cx_norm, cy_norm, width_norm, area, confidence},
    sorted by confidence descending (DNN) or area descending (Haar fallback).

    Faces whose center-y is in the bottom 15% of the frame are rejected
    (eliminates most hand/shoulder/object false positives).
    """
    _ensure_ready()
    return _detect_dnn(frame) if _use_dnn else _detect_haar(frame)


def _detect_dnn(frame: np.ndarray) -> List[dict]:
    try:
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            cv2.resize(frame, (300, 300)),
            scalefactor=1.0,
            size=(300, 300),
            mean=(104.0, 177.0, 123.0),
        )
        _dnn_net.setInput(blob)
        dets = _dnn_net.forward()

        result = []
        for i in range(dets.shape[2]):
            conf = float(dets[0, 0, i, 2])
            if conf < 0.50:
                continue

            x1 = int(max(0, dets[0, 0, i, 3] * w))
            y1 = int(max(0, dets[0, 0, i, 4] * h))
            x2 = int(min(w - 1, dets[0, 0, i, 5] * w))
            y2 = int(min(h - 1, dets[0, 0, i, 6] * h))

            if x2 <= x1 or y2 <= y1:
                continue

            cx = (x1 + x2) / 2.0 / w
            cy = (y1 + y2) / 2.0 / h

            if cy > 0.85:       # Reject bottom 15%
                continue

            result.append({
                "cx_norm": float(cx),
                "cy_norm": float(cy),
                "width_norm": float((x2 - x1) / w),
                "area": int((x2 - x1) * (y2 - y1)),
                "confidence": conf,
            })

        result.sort(key=lambda f: f["confidence"], reverse=True)
        return result

    except Exception as e:
        print(f"[FaceDetector] DNN detection error: {e}")
        return []


def _detect_haar(frame: np.ndarray) -> List[dict]:
    try:
        orig_h, orig_w = frame.shape[:2]
        scale = min(1.0, 640 / orig_w)
        if scale < 1.0:
            dw, dh = int(orig_w * scale), int(orig_h * scale)
            small = cv2.resize(frame, (dw, dh))
        else:
            small, dw, dh = frame, orig_w, orig_h

        gray = _clahe.apply(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
        haar = _get_haar()
        if haar is None:
            return []

        raw = haar.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3, minSize=(24, 24))

        result = []
        for (x, y, fw, fh) in (raw if len(raw) > 0 else []):
            cx = (x + fw / 2) / dw
            cy = (y + fh / 2) / dh
            if cy > 0.85:
                continue
            result.append({
                "cx_norm": float(cx),
                "cy_norm": float(cy),
                "width_norm": float(fw / dw),
                "area": int(fw * fh),
                "confidence": 0.70,
            })

        result.sort(key=lambda f: f["area"], reverse=True)
        return result

    except Exception as e:
        print(f"[FaceDetector] Haar detection error: {e}")
        return []


# ── Video-Wide Face Position Building ────────────────────────────────────────

def build_video_face_positions(
    video_path: str,
    total_frames: int,
    fps: float,
    scene_intervals: Optional[List[dict]] = None,
    sample_interval_s: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build per-frame face position arrays by sampling at regular intervals.

    Key design choices:
    - Interpolation is done WITHIN each scene — no cross-scene bleed
    - Outlier detection removes brief false positives (e.g. raised hand)
    - Left side (cx ≤ 0.5) → Speaker 0 / HOST
    - Right side (cx > 0.5) → Speaker 1 / GUEST

    Returns:
      left_cx  — float32[total_frames], NaN where no left-side face found
      right_cx — float32[total_frames], NaN where no right-side face found
    """
    try:
        sample_step = max(1, int(sample_interval_s * fps))
        sample_frames = list(range(0, total_frames, sample_step))

        raw_left: Dict[int, float] = {}
        raw_right: Dict[int, float] = {}

        cap = cv2.VideoCapture(video_path)
        hit = 0

        for fn in sample_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
            ret, frame = cap.read()
            if not ret:
                continue

            faces = detect_faces_in_frame(frame)
            if not faces:
                continue

            hit += 1
            # Highest-confidence face on each side
            lf = [f for f in faces if f["cx_norm"] <= 0.5]
            rf = [f for f in faces if f["cx_norm"] > 0.5]
            if lf:
                raw_left[fn] = lf[0]["cx_norm"]
            if rf:
                raw_right[fn] = rf[0]["cx_norm"]

        cap.release()
        print(
            f"[FaceDetector] {hit}/{len(sample_frames)} samples → "
            f"L:{len(raw_left)} R:{len(raw_right)}"
        )

        scenes = _to_scene_list(scene_intervals, total_frames)
        left_cx = _build_scene_aware_array(raw_left, total_frames, scenes)
        right_cx = _build_scene_aware_array(raw_right, total_frames, scenes)

        return left_cx, right_cx

    except Exception as e:
        print(f"[FaceDetector] build_video_face_positions error: {e}")
        nan = np.full(total_frames, np.nan, dtype=np.float32)
        return nan.copy(), nan.copy()


def _to_scene_list(
    scene_intervals: Optional[List[dict]],
    total_frames: int,
) -> List[Tuple[int, int]]:
    if not scene_intervals:
        return [(0, total_frames)]
    return [
        (int(s["start"]), min(int(s["end"]), total_frames))
        for s in scene_intervals
    ]


def _build_scene_aware_array(
    raw: Dict[int, float],
    total_frames: int,
    scenes: List[Tuple[int, int]],
) -> np.ndarray:
    """
    Interpolate face positions within each scene independently.
    Outlier removal: if a detection deviates > 0.25 from its neighbors, discard it.
    Between scenes: array stays NaN (no bleed).
    """
    arr = np.full(total_frames, np.nan, dtype=np.float32)

    for s_start, s_end in scenes:
        # Detections inside this scene
        scene_raw = {k: v for k, v in raw.items() if s_start <= k < s_end}
        if not scene_raw:
            continue

        keys = sorted(scene_raw.keys())
        vals = [scene_raw[k] for k in keys]

        # Outlier removal
        clean_k, clean_v = [], []
        for i, (k, v) in enumerate(zip(keys, vals)):
            nb = []
            if i > 0:
                nb.append(vals[i - 1])
            if i < len(vals) - 1:
                nb.append(vals[i + 1])
            if nb and abs(v - float(np.median(nb))) > 0.25:
                continue   # Likely false positive — skip
            clean_k.append(k)
            clean_v.append(v)

        if not clean_k:
            continue

        # Place detections at their exact sample frames
        length = s_end - s_start
        local = np.full(length, np.nan, dtype=np.float32)
        for k, v in zip(clean_k, clean_v):
            local[k - s_start] = v

        # Forward-fill only: hold last known position, no interpolation.
        # Linear interpolation between sparse samples creates artificial camera movement.
        last = np.nan
        for i in range(length):
            if not np.isnan(local[i]):
                last = local[i]
            elif not np.isnan(last):
                local[i] = last

        arr[s_start:s_end] = local

    return arr
