import json
import subprocess
from typing import Optional
from app.config import settings


def snap_to_word_boundary(target_sec: float, words: list, mode: str) -> float:
    """
    Finds the nearest word boundary to the target_sec.
    For 'start' mode: prefers word starts slightly BEFORE target (captures full first word).
    For 'end' mode: prefers word ends slightly AFTER target (keeps full last word).
    Search window: 1.5s — Nova-3 timestamps are precise enough for a tight window.
    """
    if not words:
        return target_sec

    # 1. If target is inside a word, snap to that word's boundary
    for word in words:
        w_start = word.get("start", 0)
        w_end = word.get("end", 0)
        if w_start <= target_sec <= w_end:
            return w_start if mode == "start" else w_end

    search_window = 1.5
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


def _find_sentence_end_before(hard_limit: float, clip_start: float, words: list, min_dur: int) -> Optional[float]:
    """
    Finds the end of the last sentence-ending word before hard_limit.
    Sentence endings: word.word ends with '.', '?', '!' (punctuation markers from Deepgram).
    Only returns a result if the sentence end is at least min_dur seconds after clip_start.
    Search window: up to 8s before hard_limit.
    """
    sentence_enders = {".", "?", "!", ".."}
    search_start = hard_limit - 8.0
    best = None
    for w in words:
        w_end = w.get("end", 0)
        if w_end > hard_limit:
            break
        if w_end < search_start:
            continue
        text = w.get("word", w.get("punctuated_word", "")).strip()
        if text and text[-1] in sentence_enders:
            if (w_end - clip_start) >= min_dur:
                best = w_end
    return best


def _find_prev_word_end(target_start: float, words: list) -> Optional[float]:
    """Finds the end time of the word immediately before target_start."""
    prev_end = None
    for w in words:
        w_end = w.get("end", 0)
        if w_end <= target_start:
            prev_end = w_end
        else:
            break
    return prev_end


def run(evaluated_clips: list, transcript_data: dict, video_path: str, job_id: str,
        clip_duration_min: Optional[int] = None,
        clip_duration_max: Optional[int] = None,
        channel_dna: Optional[dict] = None) -> list:
    """
    Step 7: Precision Cut (Math Only)
    Aligns clip boundaries to word boundaries using Deepgram word timestamps.
    Does NOT cut video — only calculates and stores final_start/final_end.
    Actual FFmpeg cutting happens in S08 (Export).

    Priority for duration limits: job_override > channel_dna > settings defaults.
    """
    print(f"[S07] Starting precision cut (math only) for job {job_id}. Clips: {len(evaluated_clips)}")

    words = transcript_data.get("words", [])
    if not words:
        print("[S07] Warning: No word timestamps found. Using recommended times as-is.")

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

    # Duration priority: job_override > channel_dna.duration_range > settings defaults
    dna_dur_range = (channel_dna or {}).get("duration_range", {}) if channel_dna else {}
    dna_min = dna_dur_range.get("min") if dna_dur_range else None
    dna_max = dna_dur_range.get("max") if dna_dur_range else None

    if clip_duration_max is not None:
        max_dur = int(clip_duration_max)
        dur_source = "job_override"
    elif dna_max is not None:
        max_dur = int(dna_max)
        dur_source = "channel_dna"
    else:
        max_dur = settings.MAX_CLIP_DURATION
        dur_source = "settings_default"

    if clip_duration_min is not None:
        min_dur = int(clip_duration_min)
    elif dna_min is not None:
        min_dur = int(dna_min)
    else:
        min_dur = settings.MIN_CLIP_DURATION

    print(f"[S07] Duration limits: {min_dur}s–{max_dur}s (source={dur_source})")

    results = []

    for index, clip in enumerate(evaluated_clips):
        try:
            rec_start = clip.get("recommended_start", 0.0)
            rec_end = clip.get("recommended_end", 0.0)
            content_type = clip.get("content_type", "unknown")

            # 1. Snap to word boundaries
            snapped_start = snap_to_word_boundary(rec_start, words, "start")
            snapped_end = snap_to_word_boundary(rec_end, words, "end")

            # 2. Apply breath buffers — but don't bleed into previous word
            breath_start = 0.3
            prev_end = _find_prev_word_end(snapped_start, words)
            if prev_end is not None and (snapped_start - breath_start) < prev_end:
                # Would overlap with previous word — use midpoint of gap instead
                gap = snapped_start - prev_end
                breath_start = max(gap * 0.5, 0.05)

            final_start = max(0.0, snapped_start - breath_start)
            final_end = snapped_end + 0.5

            # 3. Enforce duration limits
            duration = final_end - final_start
            if duration > max_dur:
                hard_limit = final_start + max_dur
                # Try to snap to nearest sentence end within 8s before hard limit
                sentence_end = _find_sentence_end_before(hard_limit, final_start, words, min_dur)
                if sentence_end:
                    print(f"[S07] Clip {index+1} ({content_type}): {duration:.1f}s > {max_dur}s. Smart trim to sentence end at {sentence_end:.2f}s.")
                    final_end = sentence_end + 0.3
                else:
                    print(f"[S07] Clip {index+1} ({content_type}): {duration:.1f}s > {max_dur}s. Hard trim (no sentence boundary found).")
                    final_end = hard_limit
            elif duration < min_dur:
                print(f"[S07] Warning: Clip {index+1} ({content_type}): {duration:.1f}s < {min_dur}s. Keeping anyway.")

            # 4. Clamp to video duration
            if final_end > video_duration:
                final_end = video_duration

            # 5. Skip if start >= end after clamping
            if final_start >= final_end:
                print(f"[S07] Clip {index+1} ({content_type}): start {final_start:.2f}s >= end {final_end:.2f}s after clamping. Skipping.")
                continue

            final_duration_s = final_end - final_start

            # 6. Write calculated values into clip dict
            clip_copy = dict(clip)
            clip_copy["final_start"] = round(final_start, 3)
            clip_copy["final_end"] = round(final_end, 3)
            clip_copy["final_duration_s"] = round(final_duration_s, 3)

            results.append(clip_copy)
            print(f"[S07] Clip {index+1}/{len(evaluated_clips)}: {final_start:.2f}s -> {final_end:.2f}s ({final_duration_s:.1f}s) [{content_type}]")

        except Exception as e:
            print(f"[S07] Error processing clip {index+1}: {e}")
            # Fallback: still try to snap even in exception path
            clip_copy = dict(clip)
            fb_start = clip.get("recommended_start", 0.0)
            fb_end = clip.get("recommended_end", 0.0)
            if words:
                fb_start = snap_to_word_boundary(fb_start, words, "start")
                fb_end = snap_to_word_boundary(fb_end, words, "end")
            clip_copy["final_start"] = round(max(0.0, fb_start - 0.15), 3)
            clip_copy["final_end"] = round(fb_end + 0.3, 3)
            clip_copy["final_duration_s"] = round(clip_copy["final_end"] - clip_copy["final_start"], 3)
            results.append(clip_copy)

    print(f"[S07] Precision cut complete. {len(results)}/{len(evaluated_clips)} clips processed.")
    return results
