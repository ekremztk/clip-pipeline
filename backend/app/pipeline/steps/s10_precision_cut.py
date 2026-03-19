import os
import subprocess
import json
from app.config import settings
from app.services import storage

def snap_to_word_boundary(target_sec: float, words: list, mode: str) -> float:
    """
    Finds the nearest word start or end time to the target_sec.
    Search window is 3s for start, 8s for end.
    If target_sec falls inside a word, snaps to that word's boundary.
    If no word found within window, falls back to the closest boundary to avoid mid-word cuts.
    mode: "start" or "end"
    """
    if not words:
        return target_sec

    # 1. If target_sec is inside a word, snap to that word's boundary
    for word in words:
        w_start = word.get("start", 0)
        w_end = word.get("end", 0)
        if w_start <= target_sec <= w_end:
            return w_start if mode == "start" else w_end

    best_time = target_sec
    search_window = 8.0 if mode == "end" else 3.0
    min_diff = search_window
    found = False

    for word in words:
        if mode == "start" and "start" in word:
            diff = abs(word["start"] - target_sec)
            if diff < min_diff:
                min_diff = diff
                best_time = word["start"]
                found = True
        elif mode == "end" and "end" in word:
            diff = abs(word["end"] - target_sec)
            if diff < min_diff:
                min_diff = diff
                best_time = word["end"]
                found = True

    # 2. Ensure we always snap to a valid boundary
    if not found:
        closest_diff = float('inf')
        for word in words:
            if mode == "start" and "start" in word:
                diff = abs(word["start"] - target_sec)
                if diff < closest_diff:
                    closest_diff = diff
                    best_time = word["start"]
            elif mode == "end" and "end" in word:
                diff = abs(word["end"] - target_sec)
                if diff < closest_diff:
                    closest_diff = diff
                    best_time = word["end"]

    return best_time

def run(strategy_results: list, transcript_data: dict, video_path: str, job_id: str) -> list:
    """
    Step 10: Precision Cut
    Aligns clip boundaries to word boundaries and cuts video with FFmpeg.
    """
    print(f"[S10] Starting precision cut for job {job_id}. Total clips: {len(strategy_results)}")
    
    words = transcript_data.get("words", [])
    if not words:
        print("[S10] Warning: No words found in transcript_data.")

    # Ensure output directory for job exists
    job_output_dir = os.path.join(settings.OUTPUT_DIR, job_id)
    os.makedirs(job_output_dir, exist_ok=True)

    cut_results = []

    for index, clip in enumerate(strategy_results):
        try:
            print(f"[S10] Processing clip {index+1}/{len(strategy_results)}")
            
            content_type = clip.get("content_type", "unknown")
            rec_start = clip.get("recommended_start", 0.0)
            rec_end = clip.get("recommended_end", 0.0)
            
            # 2. Snap recommended_start to nearest word start (mode="start")
            # Then subtract 0.3 seconds (natural breath buffer) but never go below 0
            snapped_start = snap_to_word_boundary(rec_start, words, "start")
            final_start = max(0.0, snapped_start - 0.3)
            
            # 3. Snap recommended_end to nearest word end (mode="end")
            # Then add 0.3 seconds buffer
            snapped_end = snap_to_word_boundary(rec_end, words, "end")
            final_end = snapped_end + 0.8
            
            # 4. Validate: end - start >= 12 and end - start <= 60
            if final_end - final_start > 60.0:
                print(f"[S10] Clip {index+1} duration > 60s. Trimming.")
                final_end = final_start + 60.0
            elif final_end - final_start < 12.0:
                print(f"[S10] Warning: Clip {index+1} duration < 12s. Proceeding anyway.")
            
            # 5. Get video duration using ffprobe
            ffprobe_cmd = [
                "ffprobe", "-v", "quiet", "-show_entries", "format=duration", 
                "-of", "json", video_path
            ]
            ffprobe_result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
            ffprobe_data = json.loads(ffprobe_result.stdout)
            video_duration = float(ffprobe_data["format"]["duration"])
            
            # Ensure end does not exceed video duration
            if final_end > video_duration:
                final_end = video_duration
                
            final_duration_s = final_end - final_start
            
            # 6. Run FFmpeg cut
            output_filename = f"clip_{index:02d}_{content_type}.mp4"
            output_path = os.path.join(job_output_dir, output_filename)
            
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-ss", str(final_start),
                "-i", video_path,
                "-t", str(final_duration_s),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                "-map", "0:v:0",
                "-map", "0:a:0",
                output_path
            ]
            
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
            
            # 7. Verify output file exists and size > 0
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                print(f"[S10] Successfully generated {output_filename}")
                # 8. Add to clip result
                clip_copy = dict(clip)
                clip_copy.update({
                    "video_landscape_path": output_path,
                    "final_start": float(final_start),
                    "final_end": float(final_end),
                    "final_duration_s": float(final_duration_s)
                })
                cut_results.append(clip_copy)
            else:
                print(f"[S10] Error: FFmpeg output file missing or empty for clip {index+1}")
                
        except subprocess.CalledProcessError as e:
            print(f"[S10] FFmpeg/ffprobe error for clip {index+1}: {e.stderr}")
        except Exception as e:
            print(f"[S10] Unexpected error processing clip {index+1}: {e}")
            
    print(f"[S10] Precision cut complete. Successfully processed {len(cut_results)}/{len(strategy_results)} clips.")
    return cut_results
