import json
import re
from typing import Optional

from app.config import settings
from app.pipeline.prompts.batch_evaluation import SYSTEM_PROMPT, EVALUATION_PROMPT
from app.pipeline.steps.s05_unified_discovery import build_channel_context
from app.services.claude_client import call_claude


# ── Transcript segment extractor ─────────────────────────────────────────────

def _words_to_natural_text(w_list: list) -> str:
    """
    Converts a list of Deepgram word objects into natural readable text.
    Uses sentence boundaries (punctuation) for line breaks with timestamps.
    Each sentence gets a [MM:SS.ss] timestamp from its first word.
    """
    if not w_list:
        return ""

    sentences = []
    current_sentence = []
    sentence_start_ts = None

    for w in w_list:
        word_text = w.get("punctuated_word", w.get("word", ""))
        if not word_text:
            continue

        if sentence_start_ts is None:
            sentence_start_ts = w.get("start", 0)

        current_sentence.append(word_text)

        # Break on sentence-ending punctuation
        if word_text and word_text[-1] in ".!?":
            ts = sentence_start_ts
            minutes = int(ts // 60)
            seconds = ts % 60
            line = f"[{minutes:02d}:{seconds:05.2f}] {' '.join(current_sentence)}"
            sentences.append(line)
            current_sentence = []
            sentence_start_ts = None

    # Flush remaining words
    if current_sentence and sentence_start_ts is not None:
        ts = sentence_start_ts
        minutes = int(ts // 60)
        seconds = ts % 60
        line = f"[{minutes:02d}:{seconds:05.2f}] {' '.join(current_sentence)}"
        sentences.append(line)

    return "\n".join(sentences)


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

        pre_words  = [w for w in words if pre_start  <= w.get("start", 0) < rec_start and w.get("end", 0) <= rec_start]
        clip_words = [w for w in words if w.get("end", 0) >= rec_start and w.get("start", 0) <= rec_end]
        post_words = [w for w in words if w.get("start", 0) > rec_end and w.get("start", 0) <= post_end]

        return {
            "pre_context":  _words_to_natural_text(pre_words),
            "clip_segment": _words_to_natural_text(clip_words),
            "post_context": _words_to_natural_text(post_words),
        }
    except Exception as e:
        print(f"[S06] Context segment error for candidate {candidate.get('candidate_id')}: {e}")
        return empty


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

        # Use word-level data with natural sentence formatting
        words = transcript_data.get("words", [])
        if words and len(words) > 10:
            segment_words = [w for w in words if w.get("start", 0) >= seg_start and w.get("end", 0) <= seg_end]
            if segment_words:
                segment = _words_to_natural_text(segment_words)
                if len(segment) > 100:
                    return segment

        # Fallback: use labeled_transcript lines within time window
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


# ── Claude message builder ────────────────────────────────────────────────────

def _build_claude_content(batch_items: list, channel_context: str, min_duration: int, max_duration: int) -> list:
    """
    Builds the Claude content array (text only) for a batch.
    Each item has:
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
            "candidate_id":       cid,
            "recommended_start":  item.get("recommended_start"),
            "recommended_end":    item.get("recommended_end"),
            "hook_text":          item.get("hook_text"),
            "end_text":           item.get("end_text"),
            "reason":             item.get("reason"),
            "primary_signal":     item.get("primary_signal"),
            "loop_potential":     item.get("loop_potential"),
            "content_type":       item.get("content_type"),
            "estimated_duration": item.get("estimated_duration"),
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

    content: list = [
        {"type": "text", "text": instructions},
        {"type": "text", "text": "\nReturn ONLY a valid JSON array — no markdown, no extra text."},
    ]
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
    min_duration: int = 12,
    max_duration: int = 60,
    full_transcript_block: Optional[list] = None,
) -> list:
    """
    Evaluates a batch of candidates with Claude using transcript only.
    Returns all evaluated candidates (pass + fixable).
    full_transcript_block: optional extra system blocks containing the full labeled transcript.
    """
    print(f"[S06] Claude batch: {len(batch_items)} candidates (text-only)")

    content = _build_claude_content(batch_items, channel_context, min_duration, max_duration)
    raw = call_claude(content, system=SYSTEM_PROMPT, extra_system_blocks=full_transcript_block)
    return _parse_claude_json(raw)


def _evaluate_single_with_claude(
    item: dict,
    channel_context: str,
    min_duration: int = 12,
    max_duration: int = 60,
    full_transcript_block: Optional[list] = None,
) -> Optional[dict]:
    try:
        results = _evaluate_batch_with_claude([item], channel_context, min_duration, max_duration, full_transcript_block)
        return results[0] if results else None
    except Exception as e:
        print(f"[S06] Single retry failed for candidate {item.get('candidate_id')}: {e}")
        return None


# ── Overlap deduplication ─────────────────────────────────────────────────────

def _deduplicate_by_overlap(clips: list, overlap_threshold: float = 0.5) -> list:
    """
    Removes temporally overlapping clips using NMS-style deduplication.
    Clips are sorted by score descending — higher-scored clip always wins.
    A candidate is dropped if it overlaps more than `overlap_threshold` of
    the shorter clip's duration with any already-kept clip.
    """
    if not clips:
        return clips

    sorted_clips = sorted(clips, key=lambda c: c.get("score", 0), reverse=True)
    kept = []

    for candidate in sorted_clips:
        c_start = float(candidate.get("recommended_start", 0) or 0)
        c_end   = float(candidate.get("recommended_end",   0) or 0)
        c_dur   = c_end - c_start
        if c_dur <= 0:
            kept.append(candidate)
            continue

        is_duplicate = False
        for kept_clip in kept:
            k_start = float(kept_clip.get("recommended_start", 0) or 0)
            k_end   = float(kept_clip.get("recommended_end",   0) or 0)

            overlap = max(0.0, min(c_end, k_end) - max(c_start, k_start))
            shorter = min(c_dur, k_end - k_start)
            if shorter > 0 and (overlap / shorter) > overlap_threshold:
                print(
                    f"[S06] Dedup: dropped candidate {candidate.get('candidate_id')} "
                    f"({c_start:.1f}s–{c_end:.1f}s, score={candidate.get('score')}) — "
                    f"{overlap:.1f}s overlap with candidate {kept_clip.get('candidate_id')} "
                    f"({k_start:.1f}s–{k_end:.1f}s, score={kept_clip.get('score')})"
                )
                is_duplicate = True
                break

        if not is_duplicate:
            kept.append(candidate)

    return kept


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
    Evaluates S05 candidates using timestamped transcripts with context windows.
    Returns ONLY pass/fixable clips — fails are dropped here, never reach S07/S08.

    clip_duration_min / clip_duration_max: job-level user selection (highest priority).
    Falls back to channel DNA, then to config defaults.

    video_path is accepted for backward compatibility but not used.
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

        # Build a cached system block with the full labeled transcript — Claude uses it
        # for hallucination detection (verifying hook_text locations) and inspector role.
        # Caching means the transcript tokens are paid once and reused across all batches.
        full_transcript_block: Optional[list] = None
        if labeled_transcript and len(labeled_transcript) > 100:
            full_transcript_block = [
                {
                    "type": "text",
                    "text": (
                        "## FULL LABELED TRANSCRIPT (for Inspector Role verification)\n"
                        "Use this to verify hook_text locations and timestamp accuracy.\n\n"
                        + labeled_transcript
                    ),
                    "cache_control": {"type": "ephemeral"},
                }
            ]

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
                "candidate_id":       candidate.get("candidate_id"),
                "timestamp":          candidate.get("timestamp", "00:00"),
                "hook_text":          candidate.get("hook_text", ""),
                "reason":             candidate.get("reason", ""),
                "primary_signal":     candidate.get("primary_signal", ""),
                "content_type":       candidate.get("content_type", ""),
                "estimated_duration": candidate.get("estimated_duration"),
                "needs_context":      candidate.get("needs_context"),
                "recommended_start":  candidate.get("recommended_start", 0),
                "recommended_end":    candidate.get("recommended_end", 0),
                "transcript_segment": segment,
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
                evaluated = _evaluate_batch_with_claude(batch, channel_context, min_duration, max_duration, full_transcript_block)

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
                            retry = _evaluate_single_with_claude(missing_item, channel_context, min_duration, max_duration, full_transcript_block)
                            if retry:
                                all_evaluated.append(retry)
                                print(f"[S06] Recovered candidate {missing_id}")
                            else:
                                print(f"[S06] Could not recover candidate {missing_id} — dropping")

            except Exception as batch_err:
                print(f"[S06] Batch {batch_num} failed: {batch_err}. Falling back to individual evaluation.")
                for item in batch:
                    try:
                        single = _evaluate_single_with_claude(item, channel_context, min_duration, max_duration, full_transcript_block)
                        if single:
                            all_evaluated.append(single)
                    except Exception as single_err:
                        print(f"[S06] Individual eval failed for candidate {item.get('candidate_id')}: {single_err}")

        print(f"[S06] Claude evaluated {len(all_evaluated)} total candidates")

        # Log hallucination flags from inspector role
        flagged = [c for c in all_evaluated if c.get("s05_hallucination_flag")]
        if flagged:
            print(f"[S06] Inspector role flagged {len(flagged)} candidates with hook_text hallucination")
            for c in flagged:
                print(f"[S06]   Candidate {c.get('candidate_id')}: {c.get('hook_text', '')[:60]}")

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

        # Deduplicate overlapping clips — keeps highest-scoring clip when two
        # candidates cover substantially the same time range (>50% overlap)
        before_dedup = len(passed)
        passed = _deduplicate_by_overlap(passed, overlap_threshold=0.5)
        if len(passed) < before_dedup:
            print(f"[S06] Overlap dedup: removed {before_dedup - len(passed)} duplicate(s), {len(passed)} remaining")

        # Sort by posting_order
        passed.sort(key=lambda c: c.get("posting_order", 999))

        # Reassign sequential posting_order
        for order, clip in enumerate(passed, start=1):
            if clip.get("posting_order") is None or clip.get("posting_order") == 999:
                clip["posting_order"] = order
            else:
                clip["posting_order"] = order  # normalize to sequential

        print(f"[S06] Final: {len(passed)} clips proceeding to S07")

        return passed

    except Exception as e:
        print(f"[S06] Critical error: {e}")
        import traceback
        traceback.print_exc()
        return []
