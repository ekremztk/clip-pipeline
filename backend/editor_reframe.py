# EDITOR MODULE — Isolated module, no dependencies on other project files
"""
Smart Reframe module.
Automatically detects faces, maps them to speakers, and generates dynamic crop data
for 16:9 to 9:16 conversion.
"""
import os
import glob
import subprocess
import shutil
import logging
from typing import Any
from collections import defaultdict

# Suppress headless warnings for MediaPipe in Railway
os.environ["DISPLAY"] = ":0"

try:
    import cv2
    import mediapipe as mp
except ImportError:
    pass  # Allow importing for type hints even if not installed locally, though we assume installed.

logger = logging.getLogger(__name__)

FACE_DETECTION_FPS = 3          # Extract 3 frames per second
EMA_ALPHA = 0.12                # Exponential moving average smoothing factor
MIN_FACE_CONFIDENCE = 0.6       # Minimum detection confidence threshold
CENTER_CROP_X = 0.5             # Fallback when no face detected
TARGET_WIDTH = 1080             # 9:16 output width
TARGET_HEIGHT = 1920            # 9:16 output height
CROP_SQUARE_SIZE = 1080         # We crop a 1080x1080 square, then scale to 1080x1920


def extract_frames(
    video_path: str,
    job_id: str,
    fps: int = FACE_DETECTION_FPS
) -> tuple[str, int]:
    """
    Extract JPEG frames from video at target FPS using FFmpeg subprocess.
    Returns (frames_dir, total_frame_count).

    FFmpeg command:
    ffmpeg -i {video_path} -vf fps={fps} -q:v 2 {frames_dir}/%04d.jpg

    - Creates /tmp/editor_{job_id}_frames/ directory
    - Uses -q:v 2 for good quality but small file size
    - Returns the frames directory path and total frame count
    - Raises RuntimeError if FFmpeg fails (log stderr)
    """
    frames_dir = f"/tmp/editor_{job_id}_frames"
    if os.path.exists(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",
        f"{frames_dir}/%04d.jpg"
    ]

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg frame extraction failed. stderr:\n{result.stderr}")
            raise RuntimeError(f"FFmpeg frame extraction failed: {result.stderr}")
    except Exception as e:
        logger.error(f"Error running FFmpeg for frame extraction: {e}")
        raise RuntimeError(f"Error extracting frames: {e}")

    frames = glob.glob(os.path.join(frames_dir, "*.jpg"))
    total_frames = len(frames)
    return frames_dir, total_frames


def detect_faces_in_frames(
    frames_dir: str,
    total_frames: int
) -> dict[int, list[dict[str, Any]]]:
    """
    Run MediaPipe face detection on all extracted JPEG frames.
    Returns dict mapping frame_index -> list of detected faces.

    Each face dict:
    {
        "x_center": float,    # 0.0-1.0 relative to frame width
        "y_center": float,    # 0.0-1.0 relative to frame height
        "width": float,       # relative bounding box width
        "height": float,      # relative bounding box height
        "confidence": float   # detection confidence 0.0-1.0
    }
    """
    face_data = {}
    
    mp_face_detection = mp.solutions.face_detection
    
    frames_processed = 0
    with mp_face_detection.FaceDetection(
        model_selection=1,
        min_detection_confidence=MIN_FACE_CONFIDENCE
    ) as face_detection:
        
        # Process frames in sorted order (1-indexed based on %04d)
        # e.g., 0001.jpg, 0002.jpg
        for frame_idx in range(1, total_frames + 1):
            frame_path = os.path.join(frames_dir, f"{frame_idx:04d}.jpg")
            if not os.path.exists(frame_path):
                continue
                
            try:
                # Load with cv2.IMREAD_COLOR
                image = cv2.imread(frame_path, cv2.IMREAD_COLOR)
                if image is None:
                    continue
                    
                # Convert BGR to RGB
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                
                results = face_detection.process(image_rgb)
                
                detected_faces = []
                if results.detections:
                    for detection in results.detections:
                        confidence = detection.score[0] if detection.score else 0.0
                        if confidence >= MIN_FACE_CONFIDENCE:
                            bbox = detection.location_data.relative_bounding_box
                            # MediaPipe returns relative bounding boxes (0.0 to 1.0)
                            x_center = bbox.xmin + bbox.width / 2.0
                            y_center = bbox.ymin + bbox.height / 2.0
                            
                            detected_faces.append({
                                "x_center": x_center,
                                "y_center": y_center,
                                "width": bbox.width,
                                "height": bbox.height,
                                "confidence": confidence
                            })
                
                # Sort detections by confidence descending
                detected_faces.sort(key=lambda x: x["confidence"], reverse=True)
                
                if detected_faces:
                    face_data[frame_idx] = detected_faces
                    
                frames_processed += 1
                if frames_processed % 30 == 0:
                    logger.info(f"Processed {frames_processed}/{total_frames} frames for face detection")
                    
            except cv2.error as e:
                logger.error(f"OpenCV error on frame {frame_idx}: {e}")
            except Exception as e:
                logger.error(f"Error processing frame {frame_idx}: {e}")
                
    return face_data


def map_speakers_to_faces(
    face_data: dict[int, list[dict[str, Any]]],
    speaker_segments: list[dict[str, Any]],
    video_metadata: dict[str, Any],
    fps: int = FACE_DETECTION_FPS
) -> dict[int, float]:
    """
    Maps each speaker_id to their typical X position in the frame.
    Returns {speaker_id: x_position_0_to_1}
    """
    try:
        if not face_data:
            logger.warning("No faces detected in any frame. Returning center fallback for all speakers.")
            # Fallback mapping
            unique_speakers = set(seg.get("speaker_id", 0) for seg in speaker_segments)
            return {speaker: CENTER_CROP_X for speaker in unique_speakers}
            
        # Collect all x_center values across the video to check for clusters
        all_x_centers = []
        for faces in face_data.values():
            if faces:
                all_x_centers.append(faces[0]["x_center"])
                
        # Simple spatial clustering for 2-speaker podcasts
        has_two_clusters = False
        left_cluster_center = 0.25
        right_cluster_center = 0.75
        
        if len(all_x_centers) > 10:
            sorted_x = sorted(all_x_centers)
            median_x = sorted_x[len(sorted_x)//2]
            
            left_xs = [x for x in all_x_centers if x < median_x]
            right_xs = [x for x in all_x_centers if x > median_x]
            
            if left_xs and right_xs:
                left_mean = sum(left_xs) / len(left_xs)
                right_mean = sum(right_xs) / len(right_xs)
                
                if right_mean - left_mean > 0.15:
                    has_two_clusters = True
                    left_cluster_center = left_mean
                    right_cluster_center = right_mean
        
        speaker_xs = {}
        
        for segment in speaker_segments:
            speaker_id = int(segment.get("speaker_id", 0))
            start_time = float(segment.get("start", 0.0))
            end_time = float(segment.get("end", 0.0))
            
            frame_start = int(start_time * fps)
            frame_end = int(end_time * fps)
            
            if speaker_id not in speaker_xs:
                speaker_xs[speaker_id] = []
            
            # Find relevant frames (1-indexed)
            for frame_idx in range(frame_start, frame_end + 1):
                faces = face_data.get(frame_idx)
                if not faces:
                    continue
                    
                # For multi-face frames and 2-speaker podcast, we can use the cluster
                best_face = faces[0]  # default to most confident
                
                if len(faces) > 1 and has_two_clusters:
                    # Find the face closest to the speaker's expected cluster
                    # If we already have some x positions for this speaker, use median
                    current_xs = speaker_xs.get(speaker_id, [])
                    if current_xs:
                        sorted_current = sorted(current_xs)
                        expected_x = sorted_current[len(sorted_current)//2]
                        best_face = min(faces, key=lambda f: abs(float(f["x_center"]) - expected_x))
                        
                if speaker_id not in speaker_xs:
                    speaker_xs[speaker_id] = []
                speaker_xs[speaker_id].append(float(best_face["x_center"]))
                    
        # Compute median for each speaker
        speaker_face_map = {}
        for speaker_id, xs in speaker_xs.items():
            if xs:
                sorted_xs = sorted(xs)
                median_x = sorted_xs[len(sorted_xs)//2]
                speaker_face_map[speaker_id] = median_x
            else:
                speaker_face_map[speaker_id] = CENTER_CROP_X
                
        # Fill in any missing speakers from segments
        unique_speakers = set(int(seg.get("speaker_id", 0)) for seg in speaker_segments)
        for speaker_id in unique_speakers:
            if speaker_id not in speaker_face_map:
                speaker_face_map[speaker_id] = CENTER_CROP_X
                
        # If there's only 1 speaker detected, but we have multiple speakers
        if len(set(speaker_face_map.values())) == 1 and len(speaker_face_map) > 1:
            # Fallback to center for everyone
            pass
            
        return speaker_face_map
        
    except Exception as e:
        logger.error(f"Error in map_speakers_to_faces: {e}")
        # Never crash — always return a valid mapping dict
        unique_speakers = set(int(seg.get("speaker_id", 0)) for seg in speaker_segments)
        return {speaker: CENTER_CROP_X for speaker in unique_speakers}


def apply_ema(values: list[float], alpha: float = EMA_ALPHA) -> list[float]:
    """
    Applies exponential moving average to a list of float values.
    Handles empty list and single-value list gracefully.
    """
    if not values:
        return []
    if len(values) == 1:
        return values
        
    smoothed = [values[0]]
    for i in range(1, len(values)):
        smoothed.append(alpha * values[i] + (1 - alpha) * smoothed[i-1])
        
    return smoothed


def generate_crop_segments(
    face_data: dict[int, list[dict[str, Any]]],
    speaker_segments: list[dict[str, Any]],
    speaker_face_map: dict[int, float],
    video_duration: float,
    src_width: int,
    fps: int = FACE_DETECTION_FPS
) -> list[dict[str, Any]]:
    """
    Generates smooth, FFmpeg-ready crop segments.
    """
    try:
        raw_crop_segments = []
        
        # Ensure we have continuous coverage over segments
        sorted_segments = sorted(speaker_segments, key=lambda x: x.get("start", 0))
        
        for segment in sorted_segments:
            speaker_id = segment.get("speaker_id", 0)
            start_time = segment.get("start", 0.0)
            end_time = segment.get("end", 0.0)
            
            frame_start = int(start_time * fps)
            frame_end = int(end_time * fps)
            
            segment_positions = []
            segment_confidences = []
            has_detection = False
            
            fallback_x = speaker_face_map.get(speaker_id, CENTER_CROP_X)
            
            # 1. Collect positions for this segment
            for frame_idx in range(frame_start, frame_end + 1):
                faces = face_data.get(frame_idx)
                if faces:
                    # Pick face closest to speaker's home position
                    best_face = min(faces, key=lambda f: abs(float(f["x_center"]) - fallback_x))
                    
                    segment_positions.append(float(best_face["x_center"]))
                    segment_confidences.append(float(best_face["confidence"]))
                    has_detection = True
                else:
                    # If no face in this frame, use last known or fallback
                    last_pos = segment_positions[-1] if segment_positions else fallback_x
                    segment_positions.append(last_pos)
                    segment_confidences.append(0.0)
            
            # 2. Apply EMA smoothing
            smoothed_positions = apply_ema(segment_positions)
            
            # If no detection for the entire segment, use fallback
            if not has_detection:
                avg_x = fallback_x
                avg_confidence = 0.0
            else:
                avg_x = sum(smoothed_positions) / len(smoothed_positions) if smoothed_positions else fallback_x
                avg_confidence = sum(segment_confidences) / len(segment_confidences) if segment_confidences else 0.0
            
            # 4. Compute crop_x_pixels
            crop_x_pixels = int(avg_x * src_width - CROP_SQUARE_SIZE / 2)
            # Clamp to edges
            crop_x_pixels = max(0, min(crop_x_pixels, src_width - CROP_SQUARE_SIZE))
            
            raw_crop_segments.append({
                "start": start_time,
                "end": end_time,
                "speaker_id": speaker_id,
                "crop_x": avg_x,
                "crop_x_pixels": crop_x_pixels,
                "detected": has_detection,
                "confidence": avg_confidence
            })
            
        # 5 & 6. Merge adjacent segments and fill gaps
        merged_segments = []
        current_time = 0.0
        
        for seg in raw_crop_segments:
            seg_start = float(seg["start"])
            seg_end = float(seg["end"])
            seg_crop_x = float(seg["crop_x"])
            seg_speaker_id = int(seg["speaker_id"])

            # Fill gap before this segment
            if seg_start > current_time + 0.1:  # small epsilon
                gap_crop = int(CENTER_CROP_X * src_width - CROP_SQUARE_SIZE / 2)
                merged_segments.append({
                    "start": current_time,
                    "end": seg_start,
                    "speaker_id": -1, # Unknown
                    "crop_x": CENTER_CROP_X,
                    "crop_x_pixels": gap_crop,
                    "detected": False,
                    "confidence": 0.0
                })
                
            # Try to merge with previous if same speaker and similar crop
            if merged_segments and merged_segments[-1]["speaker_id"] == seg_speaker_id:
                prev = merged_segments[-1]
                # If diff < 0.05 (approx 5% of width)
                if abs(float(prev["crop_x"]) - seg_crop_x) < 0.05:
                    prev["end"] = seg_end
                    current_time = seg_end
                    continue
                    
            merged_segments.append(seg)
            current_time = seg_end
            
        # Fill final gap if any
        if current_time < video_duration:
            gap_crop = int(CENTER_CROP_X * src_width - CROP_SQUARE_SIZE / 2)
            merged_segments.append({
                "start": current_time,
                "end": video_duration,
                "speaker_id": -1,
                "crop_x": CENTER_CROP_X,
                "crop_x_pixels": gap_crop,
                "detected": False,
                "confidence": 0.0
            })
            
        return merged_segments
        
    except Exception as e:
        logger.error(f"Error in generate_crop_segments: {e}")
        # Fallback to single center segment
        gap_crop = int(CENTER_CROP_X * src_width - CROP_SQUARE_SIZE / 2)
        return [{
            "start": 0.0,
            "end": video_duration,
            "speaker_id": 0,
            "crop_x": CENTER_CROP_X,
            "crop_x_pixels": max(0, min(gap_crop, src_width - CROP_SQUARE_SIZE)),
            "detected": False,
            "confidence": 0.0
        }]


def run_smart_reframe(
    job_id: str,
    video_path: str,
    speaker_segments: list[dict[str, Any]],
    video_metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    Full smart reframe pipeline. Orchestrates all 4 stages.

    Returns crop_segments list ready for FFmpeg.
    """
    frames_dir = f"/tmp/editor_{job_id}_frames"
    
    try:
        logger.info(f"[Reframe {job_id}] Stage 1: Extracting frames at {FACE_DETECTION_FPS}fps...")
        frames_dir, total_frames = extract_frames(video_path, job_id, FACE_DETECTION_FPS)
        
        if total_frames == 0:
            raise RuntimeError("No frames extracted from video")
            
        logger.info(f"[Reframe {job_id}] Stage 2: Detecting faces in {total_frames} frames...")
        face_data = detect_faces_in_frames(frames_dir, total_frames)
        
        logger.info(f"[Reframe {job_id}] Stage 3: Mapping {len(speaker_segments)} speaker segments...")
        speaker_face_map = map_speakers_to_faces(face_data, speaker_segments, video_metadata, FACE_DETECTION_FPS)
        
        logger.info(f"[Reframe {job_id}] Stage 4: Generating crop segments...")
        duration = float(video_metadata.get("duration", 0.0))
        if duration <= 0:
            # Fallback if duration is unknown (try to infer from segments)
            if speaker_segments:
                duration = max(seg.get("end", 0.0) for seg in speaker_segments) + 1.0
            else:
                duration = 60.0 # arbitrary fallback
                
        # Handle width robustly (from metadata, typical is 1920)
        src_width = video_metadata.get("width")
        if not src_width:
            src_width = 1920
        src_width = int(src_width)
            
        crop_segments = generate_crop_segments(
            face_data=face_data,
            speaker_segments=speaker_segments,
            speaker_face_map=speaker_face_map,
            video_duration=duration,
            src_width=src_width,
            fps=FACE_DETECTION_FPS
        )
        
        logger.info(f"[Reframe {job_id}] Complete: {len(crop_segments)} crop segments generated.")
        result_segments = crop_segments
        
    except Exception as e:
        logger.error(f"[Reframe {job_id}] Error in smart reframe pipeline: {e}")
        # Graceful degradation
        src_width = int(video_metadata.get("width", 1920))
        duration = float(video_metadata.get("duration", 60.0))
        if duration <= 0 and speaker_segments:
             duration = max(seg.get("end", 0.0) for seg in speaker_segments) + 1.0
             
        gap_crop = int(CENTER_CROP_X * src_width - CROP_SQUARE_SIZE / 2)
        result_segments = [{
            "start": 0.0,
            "end": max(duration, 0.1),
            "speaker_id": 0,
            "crop_x": CENTER_CROP_X,
            "crop_x_pixels": max(0, min(gap_crop, src_width - CROP_SQUARE_SIZE)),
            "detected": False,
            "confidence": 0.0
        }]
    finally:
        # Cleanup
        if os.path.exists(frames_dir):
            try:
                shutil.rmtree(frames_dir)
            except Exception as e:
                logger.error(f"Error cleaning up frames dir {frames_dir}: {e}")
                
    return result_segments
