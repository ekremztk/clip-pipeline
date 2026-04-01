"""
Frame analizi — YOLOv8 pose modeli ile kisi tespiti.
Her shot icin belirli aralikla frame ornekler ve kisilerin
pozisyonlarini (bbox merkezi) tespit eder.

Tasarim kararlari:
- Frame'ler arasi kisi eslestirmesi (IoU tracking) YAPILMIYOR
- Pose keypoints'ten yuz merkezi hesaplanmiyor, bbox merkezi kullaniliyor
- Analiz 640x360'a kucultulerek yapiliyor (hiz icin)
"""
import logging
import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .config import FrameAnalysisConfig
from .types import FrameAnalysis, PersonDetection, Shot, SHOT_WIDE, SHOT_CLOSEUP, SHOT_BROLL

logger = logging.getLogger(__name__)

# Persistent model directory — always relative to this file, never cwd
_MODELS_DIR = Path(__file__).parent.parent.parent / "models"

# Lazy-loaded model singleton
_model = None


def _get_model(model_path: str):
    """YOLOv8 modelini lazy yukle (ilk cagri). Model her zaman models/ klasorune indirilir."""
    global _model
    if _model is None:
        from ultralytics import YOLO

        _MODELS_DIR.mkdir(parents=True, exist_ok=True)

        # If model_path is relative (e.g. "yolov8s-pose.pt"), pin it to _MODELS_DIR
        p = Path(model_path)
        if not p.is_absolute():
            abs_path = _MODELS_DIR / p.name
        else:
            abs_path = p

        # Tell Ultralytics where to store downloads
        os.environ.setdefault("YOLO_CONFIG_DIR", str(_MODELS_DIR))

        _model = YOLO(str(abs_path))
        logger.info("[FrameAnalyzer] Model yuklendi: %s", abs_path)
    return _model


def analyze_shots(
    video_path: str,
    shots: list[Shot],
    src_w: int,
    src_h: int,
    config: FrameAnalysisConfig,
) -> list[FrameAnalysis]:
    """
    Her shot icin frame ornekle ve kisileri tespit et.
    Cikis: FrameAnalysis listesi (her frame icin kisi listesi).
    """
    model = _get_model(config.model_path)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("[FrameAnalyzer] Video acilamadi: %s", video_path)
        return []

    results: list[FrameAnalysis] = []
    try:
        for shot_idx, shot in enumerate(shots):
            sample_times = _get_sample_times(shot, config.sample_fps)
            for t in sample_times:
                frame = _read_frame(cap, t)
                if frame is None:
                    continue
                persons = _detect_persons(
                    model, frame, src_w, src_h, config,
                )
                results.append(FrameAnalysis(
                    time_s=t,
                    shot_index=shot_idx,
                    persons=persons,
                ))
                if persons:
                    biggest = max(persons, key=lambda p: p.area)
                    logger.info(
                        "[FrameAnalyzer] t=%.2fs shot=%d persons=%d biggest=(%.3f,%.3f)",
                        t, shot_idx, len(persons), biggest.center_x, biggest.center_y,
                    )
    finally:
        cap.release()

    logger.info("[FrameAnalyzer] Toplam %d frame analiz edildi", len(results))
    return results


# --- Ornekleme ----------------------------------------------------------------

def _get_sample_times(shot: Shot, sample_fps: float) -> list[float]:
    """
    Shot icin ornekleme zamanlarini hesapla.
    Ilk ve son 50ms'i atla (gecis artefaktlari).
    """
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

    # En az 1 sample garanti
    if not times:
        times.append(round(start, 3))
    return times


# --- Frame okuma --------------------------------------------------------------

def _read_frame(cap: cv2.VideoCapture, time_s: float) -> Optional[np.ndarray]:
    """Belirli zamandaki frame'i oku."""
    cap.set(cv2.CAP_PROP_POS_MSEC, time_s * 1000)
    ret, frame = cap.read()
    return frame if ret else None


# --- Kisi tespiti -------------------------------------------------------------

def _detect_persons(
    model,
    frame: np.ndarray,
    src_w: int,
    src_h: int,
    config: FrameAnalysisConfig,
) -> list[PersonDetection]:
    """
    YOLOv8-pose ile kisileri tespit et.
    Bbox merkezi + nose keypoint (varsa) kullaniliyor.
    Sonuclar normalize (0-1) koordinat olarak doner.
    Stable_id: X pozisyonuna gore atanir (leftmost=0).
    """
    try:
        res_w, res_h = config.analysis_resolution
        small = cv2.resize(frame, (res_w, res_h))
        scale_x = src_w / res_w
        scale_y = src_h / res_h

        results = model(small, verbose=False, conf=config.confidence_threshold)
        detections: list[PersonDetection] = []

        for result in results:
            if result.boxes is None:
                continue
            boxes = result.boxes
            has_keypoints = (
                result.keypoints is not None
                and result.keypoints.xy is not None
                and result.keypoints.conf is not None
            )

            for i in range(len(boxes)):
                # Sadece person (class 0)
                if int(boxes.cls[i]) != 0:
                    continue

                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()

                # Orijinal boyuta scale, sonra normalize
                x1_o = float(x1 * scale_x)
                y1_o = float(y1 * scale_y)
                x2_o = float(x2 * scale_x)
                y2_o = float(y2 * scale_y)

                w_norm = (x2_o - x1_o) / src_w
                h_norm = (y2_o - y1_o) / src_h
                cx = ((x1_o + x2_o) / 2) / src_w
                cy = ((y1_o + y2_o) / 2) / src_h

                # Boyut filtreleri
                if h_norm < 0.15 or w_norm < 0.04:
                    continue

                # Nose keypoint (index 0) — for face-centered framing
                face_x = None
                face_y = None
                if has_keypoints and i < len(result.keypoints.xy):
                    kps = result.keypoints.xy[i].cpu().numpy()      # (17, 2)
                    kp_conf = result.keypoints.conf[i].cpu().numpy() # (17,)
                    # Nose = keypoint 0
                    if kp_conf[0] > 0.5:
                        nose_x_px = float(kps[0][0]) * scale_x
                        nose_y_px = float(kps[0][1]) * scale_y
                        face_x = nose_x_px / src_w
                        face_y = nose_y_px / src_h

                detections.append(PersonDetection(
                    center_x=cx,
                    center_y=cy,
                    bbox_width=w_norm,
                    bbox_height=h_norm,
                    confidence=float(boxes.conf[i]),
                    face_x=face_x,
                    face_y=face_y,
                ))

        # Keep largest N by area, then sort by X for stable ordering
        detections.sort(key=lambda d: d.area, reverse=True)
        detections = detections[: config.max_persons_per_frame]

        # Assign stable_id by X position (leftmost=0, rightmost=1, ...)
        detections.sort(key=lambda d: d.center_x)
        for idx, det in enumerate(detections):
            det.stable_id = idx

        return detections

    except Exception as e:
        logger.error("[FrameAnalyzer] Tespit hatasi: %s", e)
        return []


# --- Shot Classification -----------------------------------------------------

def classify_shots(
    shots: list[Shot],
    frame_analyses: list[FrameAnalysis],
) -> list[Shot]:
    """
    Classify each shot based on YOLO person counts.

    Uses majority vote from all frames in the shot:
      - Most frames have 2+ persons → "wide"
      - Most frames have 1 person  → "closeup"
      - Most frames have 0 persons → "b_roll"

    Mutates shot.shot_type in-place and returns the same list.
    """
    for shot_idx, shot in enumerate(shots):
        # Collect person counts for all frames in this shot
        counts = [
            len(fa.persons)
            for fa in frame_analyses
            if fa.shot_index == shot_idx
        ]

        if not counts:
            shot.shot_type = SHOT_BROLL
            continue

        # Majority vote
        wide_count = sum(1 for c in counts if c >= 2)
        single_count = sum(1 for c in counts if c == 1)
        empty_count = sum(1 for c in counts if c == 0)

        total = len(counts)
        if wide_count > total / 2:
            shot.shot_type = SHOT_WIDE
        elif single_count > total / 2:
            shot.shot_type = SHOT_CLOSEUP
        elif empty_count > total / 2:
            shot.shot_type = SHOT_BROLL
        elif wide_count >= single_count:
            shot.shot_type = SHOT_WIDE
        else:
            shot.shot_type = SHOT_CLOSEUP

        logger.info(
            "[ShotClassifier] Shot %d (%.1f-%.1fs): %s (frames: %d wide, %d single, %d empty)",
            shot_idx, shot.start_s, shot.end_s, shot.shot_type,
            wide_count, single_count, empty_count,
        )

    return shots
