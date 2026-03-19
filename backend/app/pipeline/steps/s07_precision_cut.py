import json
import subprocess
from app.config import settings


def snap_to_word_boundary(target_sec: float, words: list, mode: str) -> float:
    """
    Finds the nearest word boundary to the target_sec.
    For 'start' mode: prefers word starts slightly BEFORE target (captures full first word).
    For 'end' mode: prefers word ends slightly AFTER target (keeps full last word).
    Search window: 3s in both directions.
    
    This function is copied exactly from s10_precision_cut.py — proven logic, do not modify.
    """
    if not words:
        return target_sec

    # 1. If target is inside a word, snap to that word's boundary
    for word in words:
        w_start = word.get("start", 0)
        w_end = word.get("end", 0)
        if w_start <= target_sec <= w_end:
            return w_start if mode == "start" else w_end

    search_window = 3.0
    best_time = target_sec
    best_score = float('inf')

    for word in words:
        if mode == "start" and "start" in word:
            diff = word["start"] - target_sec
            abs_diff = abs(diff)
            if abs_diff > search_window:
                continue
            score = abs_diff * (1.5 if diff > 0 else 1.0)
            if score < best_score:
                best_score = score
                best_time = word["start"]

        elif mode == "end" and "end" in word:
            diff = word["end"] - target_sec
            abs_diff = abs(diff)
            if abs_diff > search_window:
                continue
            score = abs_diff * (1.5 if diff < 0 else 1.0)
            if score < best_score:
                best_score = score
                best_time = word["end"]

    return best_time


def run(evaluated_clips: list, transcript_data: dict, video_path: str, job_id: str) -> list:
    """
    Step 7: Precision Cut (Math Only)
    Aligns clip boundaries to word boundaries using Deepgram word timestamps.
    Does NOT cut video — only calculates and stores final_start/final_end.
    Actual FFmpeg cutting happens in S08 (Export).
    """
    print(f"[S07] Starting precision cut (math only) for job {job_id}. Clips: {len(evaluated_clips)}")

    words = transcript_data.get("words", [])
    if not words:
        print("[S07] Warning: No word timestamps found. Using Gemini's recommended times as-is.")

    # Get video duration via ffprobe (needed to clamp end times)
    video_duration = 999999.0
    try:
        ffprobe_cmd = [
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "json", video_path
        ]
        ffprobe_result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        ffprobe_data = json.loads(ffprobe_result.stdout)
        video_duration = float(ffprobe_data["format"]["duration"])
        print(f"[S07] Video duration: {video_duration:.1f}s")
    except Exception as e:
        print(f"[S07] Warning: Could not get video duration: {e}")

    max_dur = settings.MAX_CLIP_DURATION  # 60
    min_dur = settings.MIN_CLIP_DURATION  # 12

    results = []

    for index, clip in enumerate(evaluated_clips):
        try:
            rec_start = clip.get("recommended_start", 0.0)
            rec_end = clip.get("recommended_end", 0.0)
            content_type = clip.get("content_type", "unknown")

            # 1. Snap to word boundaries
            snapped_start = snap_to_word_boundary(rec_start, words, "start")
            snapped_end = snap_to_word_boundary(rec_end, words, "end")

            # 2. Apply breath buffers
            final_start = max(0.0, snapped_start - 0.3)
            final_end = snapped_end + 0.5

            # 3. Enforce duration limits
            duration = final_end - final_start
            if duration > max_dur:
                print(f"[S07] Clip {index+1} ({content_type}): {duration:.1f}s > {max_dur}s. Trimming end.")
                final_end = final_start + max_dur
            elif duration < min_dur:
                print(f"[S07] Warning: Clip {index+1} ({content_type}): {duration:.1f}s < {min_dur}s. Keeping anyway.")

            # 4. Clamp to video duration
            if final_end > video_duration:
                final_end = video_duration

            final_duration_s = final_end - final_start

            # 5. Write calculated values into clip dict
            clip_copy = dict(clip)
            clip_copy["final_start"] = round(final_start, 3)
            clip_copy["final_end"] = round(final_end, 3)
            clip_copy["final_duration_s"] = round(final_duration_s, 3)

            results.append(clip_copy)
            print(f"[S07] Clip {index+1}/{len(evaluated_clips)}: {final_start:.2f}s -> {final_end:.2f}s ({final_duration_s:.1f}s) [{content_type}]")

        except Exception as e:
            print(f"[S07] Error processing clip {index+1}: {e}")
            # Still include the clip with original times as fallback
            clip_copy = dict(clip)
            clip_copy["final_start"] = clip.get("recommended_start", 0.0)
            clip_copy["final_end"] = clip.get("recommended_end", 0.0)
            clip_copy["final_duration_s"] = clip_copy["final_end"] - clip_copy["final_start"]
            results.append(clip_copy)

    print(f"[S07] Precision cut complete. {len(results)}/{len(evaluated_clips)} clips processed.")
    return results
