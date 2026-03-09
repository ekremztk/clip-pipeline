"""
reframer.py — 9:16 auto-reframe
MediaPipe varsa yüz takibi, yoksa merkezi kırpma.
"""

import subprocess
import json
from pathlib import Path

MEDIAPIPE_AVAILABLE = False
try:
    import cv2
    import numpy as np
    import mediapipe as mp
    if hasattr(mp, 'solutions') and hasattr(mp.solutions, 'face_detection'):
        MEDIAPIPE_AVAILABLE = True
    else:
        print("[Reframer] MediaPipe sürümü uyumsuz, merkezi kırpma kullanılacak.")
except ImportError:
    print("[Reframer] MediaPipe kurulu değil, merkezi kırpma kullanılacak.")


def reframe_to_vertical(input_path: str, output_path: str, smoothing: float = 0.08) -> str:
    if not MEDIAPIPE_AVAILABLE:
        return _center_crop(input_path, output_path)

    print(f"[Reframer] 9:16 reframe başlıyor: {input_path}")

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        return _center_crop(input_path, output_path)

    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target_w = min(int(src_h * 9 / 16), src_w)

    print(f"[Reframer] {src_w}x{src_h} → {target_w}x{src_h} ({fps:.1f}fps)")

    face_x_positions = _detect_faces(cap, src_w, src_h, total_frames)
    cap.release()

    smoothed_x = _smooth_positions(face_x_positions, src_w, target_w, smoothing)
    success = _render_with_ffmpeg(input_path, output_path, smoothed_x, src_w, src_h, target_w, src_h, fps)

    if success:
        print(f"[Reframer] ✅ {output_path}")
        return output_path
    return _center_crop(input_path, output_path)


def _detect_faces(cap, src_w, src_h, total_frames):
    face_x_positions = []
    default_x = src_w // 2

    with mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.5
    ) as fd:
        frame_no = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_no += 1

            if frame_no % 3 != 0:
                face_x_positions.append(face_x_positions[-1] if face_x_positions else default_x)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = fd.process(rgb)

            if results.detections:
                best = max(results.detections, key=lambda d: d.location_data.relative_bounding_box.width)
                bbox = best.location_data.relative_bounding_box
                cx = int((bbox.xmin + bbox.width / 2) * src_w)
                face_x_positions.append(cx)
            else:
                face_x_positions.append(face_x_positions[-1] if face_x_positions else default_x)

    return face_x_positions


def _smooth_positions(raw, src_w, target_w, smoothing):
    if not raw:
        return []
    half_w = target_w // 2
    min_x, max_x = half_w, src_w - half_w
    smoothed = []
    current = float(raw[0])
    for t in raw:
        current = current + smoothing * (t - current)
        smoothed.append(max(min_x, min(max_x, int(current))))
    return smoothed


def _render_with_ffmpeg(input_path, output_path, x_positions, src_w, src_h, target_w, target_h, fps):
    if not x_positions:
        return False
    avg_x = int(sum(x_positions) / len(x_positions))
    crop_x = max(0, min(src_w - target_w, avg_x - target_w // 2))

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"crop={target_w}:{target_h}:{crop_x}:0,scale=1080:1920",
        "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", "-crf", "18",
        output_path
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def _center_crop(input_path: str, output_path: str) -> str:
    print("[Reframer] Merkezi kırpma uygulanıyor...")
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920",
        "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", "-crf", "18",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[Reframer] Hata: {result.stderr[:200]}")
        return input_path
    return output_path


def get_video_dimensions(video_path: str) -> tuple:
    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "stream=width,height", "-of", "json", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        streams = json.loads(result.stdout).get("streams", [{}])
        if streams:
            return streams[0].get("width", 1920), streams[0].get("height", 1080)
    return 1920, 1080


def is_already_vertical(video_path: str) -> bool:
    w, h = get_video_dimensions(video_path)
    return h > w