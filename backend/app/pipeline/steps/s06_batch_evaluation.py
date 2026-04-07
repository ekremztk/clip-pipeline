import base64
import json
import os
import re
import subprocess
import tempfile
from typing import Optional

from app.config import settings
from app.pipeline.prompts.batch_evaluation import SYSTEM_PROMPT, EVALUATION_PROMPT
from app.pipeline.steps.s05_unified_discovery import build_channel_context
from app.services.claude_client import call_claude
from app.director.events import director_events


# ── Transcript segment extractor (unchanged from previous version) ────────────

def _extract_context_segments(
    candidate: dict,
    transcript_data: dict,
    context_seconds: float = 20.0,
) -> dict:
    """
    Extracts three transcript sections for context boundary analysis:
      - pre_context  : context_seconds immediately BEFORE recommended_start
      - clip_segment : recommended_start → recommended_end (the candidate itself)
      - post_context : recommended_end → recommended_end + context_seconds

    Returns {"pre_context": str, "clip_segment": str, "post_context": str}.
    All values are empty strings on failure — caller falls back to transcript_segment.
    """
    empty = {"pre_context": "", "clip_segment": "", "post_context": ""}
    try:
        rec_start = float(candidate.get("recommended_start", 0))
        rec_end   = float(candidate.get("recommended_end",   0))
        if rec_end <= rec_start:
            return empty

        pre_start = max(0.0, rec_start - context_seconds)
        post_end  = rec_end + context_seconds

        words = transcript_data.get("words", [])
        if not words or len(words) <= 10:
            return empty

        def words_to_timestamped_text(w_list: list) -> str:
            if not w_list:
                return ""
            lines, current_line_words, last_ts = [], [], None
            for i, w in enumerate(w_list):
                if i % 10 == 0:
                    ts = w.get("start", 0)
                    if last_ts is None or ts - last_ts >= 2.0:
                        if current_line_words:
                            lines.append(" ".join(current_line_words))
                            current_line_words = []
                        minutes = int(ts // 60)
                        seconds = ts % 60
                        current_line_words.append(f"[{minutes:02d}:{seconds:05.2f}]")
                        last_ts = ts
                current_line_words.append(w.get("punctuated_word", w.get("word", "")))
            if current_line_words:
                lines.append(" ".join(current_line_words))
            return "\n".join(lines)

        pre_words  = [w for w in words if pre_start  <= w.get("start", 0) <  rec_start]
        clip_words = [w for w in words if rec_start  <= w.get("start", 0) <= rec_end]
        post_words = [w for w in words if rec_end    <  w.get("start", 0) <= post_end]

        return {
            "pre_context":  words_to_timestamped_text(pre_words),
            "clip_segment": words_to_timestamped_text(clip_words),
            "post_context": words_to_timestamped_text(post_words),
        }
    except Exception as e:
        print(f"[S06] Context segment error for candidate {candidate.get('candidate_id')}: {e}")
        return empty


def _extract_context_frames(video_path: str, candidate: dict) -> dict:
    """
    Extracts one frame ~10s before recommended_start and one frame ~10s after
    recommended_end for context boundary analysis.
    Returns {"pre_frame": frame_dict | None, "post_frame": frame_dict | None}.
    Always non-fatal.
    """
    result = {"pre_frame": None, "post_frame": None}
    if not video_path or not os.path.exists(video_path):
        return result

    rec_start = float(candidate.get("recommended_start", 0))
    rec_end   = float(candidate.get("recommended_end",   rec_start + 30))
    cid       = candidate.get("candidate_id", "x")

    def _single_frame(ts: float, label: str):
        if ts < 0:
            ts = 0.0
        tmp_path = os.path.join(tempfile.gettempdir(), f"s06_ctx_{cid}_{label}.jpg")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
                 "-vframes", "1", "-q:v", "3", "-vf", "scale=768:-1", tmp_path],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                with open(tmp_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")
                return {"data": img_b64, "media_type": "image/jpeg",
                        "label": label, "timestamp": round(ts, 2)}
        except Exception as e:
            print(f"[S06] Context frame failed at {ts:.1f}s (candidate {cid}): {e}")
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
        return None

    result["pre_frame"]  = _single_frame(rec_start - 10.0, "pre_context")
    result["post_frame"] = _single_frame(rec_end   + 10.0, "post_context")
    return result


def _extract_transcript_segment(
    candidate: dict,
    labeled_transcript: str,
    transcript_data: dict,
    window_seconds: float = 120.0,
) -> str:
    try:
        rec_start = candidate.get("recommended_start", 0)
        rec_end = candidate.get("recommended_end", 0)
        center = (rec_start + rec_end) / 2 if rec_start and rec_end else 0

        if center == 0:
            ts_str = candidate.get("timestamp", "00:00")
            parts = ts_str.split(":")
            try:
                if len(parts) == 2:
                    center = float(parts[0]) * 60 + float(parts[1])
                elif len(parts) == 3:
                    center = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            except (ValueError, TypeError):
                center = 0

        if center == 0:
            return labeled_transcript[:3000]

        seg_start = max(0, center - window_seconds)
        seg_end = center + window_seconds

        words = transcript_data.get("words", [])
        if words and len(words) > 10:
            segment_words = [w for w in words if w.get("start", 0) >= seg_start and w.get("end", 0) <= seg_end]

            if segment_words:
                lines, current_line_words, last_ts = [], [], None
                for i, w in enumerate(segment_words):
                    if i % 10 == 0:
                        ts = w.get("start", 0)
                        if last_ts is None or ts - last_ts >= 2.0:
                            if current_line_words:
                                lines.append(" ".join(current_line_words))
                                current_line_words = []
                            minutes = int(ts // 60)
                            seconds = ts % 60
                            current_line_words.append(f"[{minutes:02d}:{seconds:05.2f}]")
                            last_ts = ts
                    current_line_words.append(w.get("punctuated_word", w.get("word", "")))
                if current_line_words:
                    lines.append(" ".join(current_line_words))
                segment = "\n".join(lines)
                if len(segment) > 100:
                    return segment

        pattern = re.compile(r'\[(\d+):(\d+\.?\d*)\]')
        segment_lines = []
        for line in labeled_transcript.split("\n"):
            match = pattern.search(line)
            if match:
                line_ts = float(match.group(1)) * 60 + float(match.group(2))
                if seg_start <= line_ts <= seg_end:
                    segment_lines.append(line)
        if segment_lines:
            return "\n".join(segment_lines)

        return labeled_transcript[:3000]

    except Exception as e:
        print(f"[S06] Transcript segment error for candidate {candidate.get('candidate_id')}: {e}")
        return labeled_transcript[:3000]


# ── Frame extractor ───────────────────────────────────────────────────────────

def _extract_frames(video_path: str, candidate: dict, num_frames: int = 4) -> list:
    """
    Extracts num_frames frames from the candidate's time range using FFmpeg.
    Returns list of {"data": base64_str, "media_type": "image/jpeg", "label": str, "timestamp": float}
    Returns empty list on failure (non-fatal — Claude will evaluate text-only).
    """
    frames = []
    rec_start = float(candidate.get("recommended_start", 0))
    rec_end = float(candidate.get("recommended_end", rec_start + 30))
    duration = rec_end - rec_start

    if duration <= 0 or not video_path or not os.path.exists(video_path):
        return []

    labels = ["hook", "early", "middle", "final"]
    # hook at 0.5s in, early at 25%, middle at 50%, final at 90%
    offsets = [0.5, duration * 0.25, duration * 0.5, duration * 0.90]

    cid = candidate.get("candidate_id", "x")
    tmp_dir = tempfile.gettempdir()

    for i, (offset, label) in enumerate(zip(offsets[:num_frames], labels[:num_frames])):
        ts = round(rec_start + min(max(offset, 0), duration - 0.1), 3)
        tmp_path = os.path.join(tmp_dir, f"s06_frame_{cid}_{i}.jpg")
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", str(ts),
                    "-i", video_path,
                    "-vframes", "1",
                    "-q:v", "3",
                    "-vf", "scale=768:-1",
                    tmp_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                with open(tmp_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")
                frames.append({
                    "data": img_b64,
                    "media_type": "image/jpeg",
                    "label": label,
                    "timestamp": ts,
                })
        except Exception as e:
            print(f"[S06] Frame extraction failed at {ts}s (candidate {cid}): {e}")
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    return frames


# ── Claude message builder ────────────────────────────────────────────────────

def _build_claude_content(batch_items: list, channel_context: str, min_duration: int, max_duration: int) -> list:
    """
    Builds the Claude content array (text + images interleaved) for a batch.
    Each item may have:
      - "frames"       : clip frames (hook/early/middle/final)
      - "pre_frame"    : context frame before the clip
      - "post_frame"   : context frame after the clip
      - "pre_context"  : transcript 20s before recommended_start
      - "clip_segment" : transcript for the clip itself
      - "post_context" : transcript 20s after recommended_end
      - "transcript_segment": fallback transcript (used when context unavailable)
    """
    candidates_text_parts = []
    for item in batch_items:
        cid = item.get("candidate_id")

        # Use structured 3-part transcript if available, else fallback
        has_context = bool(item.get("clip_segment") or item.get("pre_context") or item.get("post_context"))
        if has_context:
            transcript_block = (
                f"PRE_CONTEXT (20s before clip — check if story starts earlier):\n"
                f"{item.get('pre_context') or '(none)'}\n\n"
                f"CLIP_TRANSCRIPT (the proposed {item.get('recommended_start')}s–{item.get('recommended_end')}s window):\n"
                f"{item.get('clip_segment') or '(none)'}\n\n"
                f"POST_CONTEXT (20s after clip — check if arc finishes later):\n"
                f"{item.get('post_context') or '(none)'}"
            )
        else:
            transcript_block = item.get("transcript_segment", "")

        meta = {
            "candidate_id":      cid,
            "timestamp":         item.get("timestamp"),
            "hook_text":         item.get("hook_text"),
            "reason":            item.get("reason"),
            "primary_signal":    item.get("primary_signal"),
            "content_type":      item.get("content_type"),
            "recommended_start": item.get("recommended_start"),
            "recommended_end":   item.get("recommended_end"),
        }
        candidates_text_parts.append(
            f"CANDIDATE {cid}:\n{json.dumps(meta, indent=2)}\n\nTRANSCRIPT:\n{transcript_block}"
        )

    candidates_block = "\n\n---\n\n".join(candidates_text_parts)

    instructions = EVALUATION_PROMPT.replace(
        "CHANNEL_CONTEXT_PLACEHOLDER", channel_context
    ).replace(
        "CANDIDATES_PLACEHOLDER", candidates_block
    ).replace(
        "MIN_DURATION_PLACEHOLDER", str(min_duration)
    ).replace(
        "MAX_DURATION_PLACEHOLDER", str(max_duration)
    )

    content: list = [{"type": "text", "text": instructions}]

    # Interleave clip frames + context frames per candidate
    has_any_frames = any(
        item.get("frames") or item.get("pre_frame") or item.get("post_frame")
        for item in batch_items
    )
    if has_any_frames:
        content.append({"type": "text", "text": "\n\n## VIDEO FRAMES PER CANDIDATE\n"})
        for item in batch_items:
            cid    = item.get("candidate_id")
            frames = item.get("frames", [])
            pre_f  = item.get("pre_frame")
            post_f = item.get("post_frame")

            if not frames and not pre_f and not post_f:
                continue

            content.append({"type": "text", "text": f"\n### CANDIDATE {cid} frames:"})

            # Pre-context frame first
            if pre_f:
                content.append({"type": "text", "text": f"[{pre_f['label']} @ {pre_f['timestamp']}s — BEFORE clip]"})
                content.append({"type": "image", "source": {"type": "base64", "media_type": pre_f["media_type"], "data": pre_f["data"]}})

            # Clip frames
            for frame in frames:
                content.append({"type": "text", "text": f"[{frame['label']} @ {frame['timestamp']}s]"})
                content.append({"type": "image", "source": {"type": "base64", "media_type": frame["media_type"], "data": frame["data"]}})

            # Post-context frame last
            if post_f:
                content.append({"type": "text", "text": f"[{post_f['label']} @ {post_f['timestamp']}s — AFTER clip]"})
                content.append({"type": "image", "source": {"type": "base64", "media_type": post_f["media_type"], "data": post_f["data"]}})

    content.append({"type": "text", "text": "\nReturn ONLY a valid JSON array — no markdown, no extra text."})
    return content


# ── JSON parser ───────────────────────────────────────────────────────────────

def _parse_claude_json(raw: str) -> list:
    if not raw:
        return []
    cleaned = raw.strip()
    # Strip markdown fences just in case
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = re.sub(r'[\x00-\x1f\x7f]', '', cleaned.strip())
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict):
            for key in ("candidates", "evaluated", "results"):
                if key in result and isinstance(result[key], list):
                    return [item for item in result[key] if isinstance(item, dict)]
    except json.JSONDecodeError as e:
        print(f"[S06] Claude JSON parse error: {e}")
        print(f"[S06] Raw snippet: {cleaned[:400]}")
    return []


# ── Core evaluation logic ─────────────────────────────────────────────────────

def _evaluate_batch_with_claude(
    batch_items: list,
    channel_context: str,
    video_path: Optional[str],
    min_duration: int = 12,
    max_duration: int = 60,
) -> list:
    """
    Evaluates a batch of candidates with Claude.
    Extracts frames if video_path is available.
    Returns all evaluated candidates (pass + fixable + fail).
    """
    # Extract clip frames + context frames for each item
    for item in batch_items:
        if video_path:
            item["frames"] = _extract_frames(video_path, item)
            ctx_frames = _extract_context_frames(video_path, item)
            item["pre_frame"]  = ctx_frames["pre_frame"]
            item["post_frame"] = ctx_frames["post_frame"]
        else:
            item["frames"]     = []
            item["pre_frame"]  = None
            item["post_frame"] = None

    has_any_frames = any(item.get("frames") for item in batch_items)
    has_ctx_frames = any(item.get("pre_frame") or item.get("post_frame") for item in batch_items)
    print(f"[S06] Claude batch: {len(batch_items)} candidates, clip_frames={'yes' if has_any_frames else 'no'}, context_frames={'yes' if has_ctx_frames else 'no'}")

    content = _build_claude_content(batch_items, channel_context, min_duration, max_duration)
    raw = call_claude(content, system=SYSTEM_PROMPT)
    return _parse_claude_json(raw)


def _evaluate_single_with_claude(
    item: dict,
    channel_context: str,
    video_path: Optional[str],
    min_duration: int = 12,
    max_duration: int = 60,
) -> Optional[dict]:
    try:
        results = _evaluate_batch_with_claude([item], channel_context, video_path, min_duration, max_duration)
        return results[0] if results else None
    except Exception as e:
        print(f"[S06] Single retry failed for candidate {item.get('candidate_id')}: {e}")
        return None


# ── Main run function ─────────────────────────────────────────────────────────

def run(
    candidates: list,
    labeled_transcript: str,
    transcript_data: dict,
    channel_dna: dict,
    channel_id: str,
    job_id: str,
    video_path: Optional[str] = None,
    clip_duration_min: Optional[int] = None,
    clip_duration_max: Optional[int] = None,
) -> list:
    """
    S06: Batch Evaluation (Claude Sonnet)
    Evaluates S05 candidates using video frames + timestamped transcripts.
    Returns ONLY pass/fixable clips — fails are dropped here, never reach S07/S08.

    clip_duration_min / clip_duration_max: job-level user selection (highest priority).
    Falls back to channel DNA, then to config defaults.
    """
    # Resolve effective duration limits: job-level > channel DNA > config
    min_duration = int(
        clip_duration_min
        if clip_duration_min is not None
        else channel_dna.get("duration_range", {}).get("min", settings.MIN_CLIP_DURATION)
    )
    max_duration = int(
        clip_duration_max
        if clip_duration_max is not None
        else channel_dna.get("duration_range", {}).get("max", settings.MAX_CLIP_DURATION)
    )
    print(f"[S06] Duration limits: {min_duration}s–{max_duration}s (job_override={'yes' if clip_duration_min is not None else 'no'})")
    print(f"[S06] Starting Claude evaluation for job {job_id}: {len(candidates)} candidates")

    if not candidates:
        print("[S06] No candidates. Returning empty list.")
        return []

    try:
        channel_context = build_channel_context(channel_dna, channel_id)

        # Build batch items with transcript segments + context windows
        all_batch_data = []
        for candidate in candidates:
            segment  = _extract_transcript_segment(candidate, labeled_transcript, transcript_data)
            ctx_segs = _extract_context_segments(candidate, transcript_data)

            # Skip candidates with no transcript content — Claude cannot evaluate them
            has_content = bool(
                segment or ctx_segs["clip_segment"] or
                ctx_segs["pre_context"] or ctx_segs["post_context"]
            )
            if not has_content:
                print(f"[S06] Skipping candidate {candidate.get('candidate_id')}: no transcript content (start={candidate.get('recommended_start')}, end={candidate.get('recommended_end')})")
                continue

            all_batch_data.append({
                "candidate_id":      candidate.get("candidate_id"),
                "timestamp":         candidate.get("timestamp", "00:00"),
                "hook_text":         candidate.get("hook_text", ""),
                "reason":            candidate.get("reason", ""),
                "primary_signal":    candidate.get("primary_signal", ""),
                "content_type":      candidate.get("content_type", ""),
                "recommended_start": candidate.get("recommended_start", 0),
                "recommended_end":   candidate.get("recommended_end", 0),
                "transcript_segment": segment,          # fallback
                "pre_context":        ctx_segs["pre_context"],
                "clip_segment":       ctx_segs["clip_segment"],
                "post_context":       ctx_segs["post_context"],
            })

        # Evaluate in batches of 4 — smaller batches prevent Claude from missing candidates
        batch_size = 4
        all_evaluated = []

        for i in range(0, len(all_batch_data), batch_size):
            batch = all_batch_data[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(all_batch_data) + batch_size - 1) // batch_size
            print(f"[S06] Batch {batch_num}/{total_batches} ({len(batch)} candidates)")

            try:
                evaluated = _evaluate_batch_with_claude(batch, channel_context, video_path, min_duration, max_duration)

                returned_ids = {str(item.get("candidate_id", "")) for item in evaluated}
                sent_ids = {str(item.get("candidate_id", "")) for item in batch}
                missing_ids = sent_ids - returned_ids

                all_evaluated.extend(evaluated)

                if missing_ids:
                    print(f"[S06] Batch {batch_num}: Claude missed {len(missing_ids)} candidates — retrying: {missing_ids}")
                    for missing_id in missing_ids:
                        missing_item = next(
                            (item for item in batch if str(item.get("candidate_id")) == missing_id),
                            None,
                        )
                        if missing_item:
                            retry = _evaluate_single_with_claude(missing_item, channel_context, video_path, min_duration, max_duration)
                            if retry:
                                all_evaluated.append(retry)
                                print(f"[S06] Recovered candidate {missing_id}")
                            else:
                                print(f"[S06] Could not recover candidate {missing_id} — dropping")

            except Exception as batch_err:
                print(f"[S06] Batch {batch_num} failed: {batch_err}. Falling back to individual evaluation.")
                for item in batch:
                    try:
                        single = _evaluate_single_with_claude(item, channel_context, video_path, min_duration, max_duration)
                        if single:
                            all_evaluated.append(single)
                    except Exception as single_err:
                        print(f"[S06] Individual eval failed for candidate {item.get('candidate_id')}: {single_err}")

        print(f"[S06] Claude evaluated {len(all_evaluated)} total candidates")

        # Safety filter — fails should not appear in output (Claude omits them), but guard anyway
        passed = []
        for clip in all_evaluated:
            verdict = clip.get("quality_verdict", "")
            if verdict in ("pass", "fixable"):
                notes = clip.get("quality_notes", "")
                if verdict == "fixable" and notes:
                    print(f"[S06] Fixable candidate {clip.get('candidate_id', '?')}: {notes}")
                passed.append(clip)
            else:
                print(f"[S06] Safety-filtered unexpected verdict for candidate {clip.get('candidate_id', '?')}: '{verdict}'")

        print(f"[S06] Quality gate: {len(passed)} passed, {len(all_evaluated) - len(passed)} filtered")

        # Clamp adjusted boundaries to video duration — prevents start > video_end
        video_duration = float(transcript_data.get("duration", 0.0)) if transcript_data else 0.0
        if video_duration > 0:
            clamped_passed = []
            for clip in passed:
                clip_start = float(clip.get("recommended_start", 0) or 0)
                clip_end = float(clip.get("recommended_end", 0) or 0)
                clip_end = min(clip_end, video_duration)
                clip_start = min(clip_start, video_duration)
                if clip_end - clip_start < min_duration:
                    print(f"[S06] Dropping candidate {clip.get('candidate_id')}: {clip_end - clip_start:.1f}s after clamping to video bounds ({video_duration:.1f}s)")
                    continue
                clip["recommended_start"] = round(clip_start, 3)
                clip["recommended_end"] = round(clip_end, 3)
                clamped_passed.append(clip)
            passed = clamped_passed

        if not passed:
            print("[S06] No candidates passed quality gate.")
            return []

        # Sort by posting_order
        passed.sort(key=lambda c: c.get("posting_order", 999))

        # Reassign sequential posting_order
        for order, clip in enumerate(passed, start=1):
            if clip.get("posting_order") is None or clip.get("posting_order") == 999:
                clip["posting_order"] = order
            else:
                clip["posting_order"] = order  # normalize to sequential

        print(f"[S06] Final: {len(passed)} clips proceeding to S07")

        try:
            director_events.emit_sync(
                module="module_1", event="s06_evaluation_completed",
                payload={
                    "job_id": job_id,
                    "pass_count": len(passed),
                    "fail_count": len(failed_log),
                    "total_evaluated": len(all_evaluated),
                },
                channel_id=channel_id,
            )
        except Exception:
            pass

        return passed

    except Exception as e:
        print(f"[S06] Critical error: {e}")
        import traceback
        traceback.print_exc()
        return []
