import json
import re
from typing import Optional
from app.config import settings
from app.services.gemini_client import generate_json
from app.pipeline.prompts.batch_evaluation import PROMPT
from app.pipeline.steps.s05_unified_discovery import build_channel_context
from app.director.events import director_events


def _extract_transcript_segment(
    candidate: dict,
    labeled_transcript: str,
    transcript_data: dict,
    window_seconds: float = 120.0
) -> str:
    """
    Extracts ±2 minute transcript segment around the candidate's timestamp.
    Uses word-level timestamps from Deepgram for precision.
    Falls back to line-based extraction if word timestamps unavailable.
    """
    try:
        # Get candidate center timestamp
        rec_start = candidate.get("recommended_start", 0)
        rec_end = candidate.get("recommended_end", 0)
        center = (rec_start + rec_end) / 2 if rec_start and rec_end else 0

        # If center is 0, try parsing from MM:SS timestamp
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
            return labeled_transcript[:3000]  # Fallback: first 3000 chars

        seg_start = max(0, center - window_seconds)
        seg_end = center + window_seconds

        # Method 1: Word-level extraction (preferred — includes timestamps)
        words = transcript_data.get("words", [])
        if words and len(words) > 10:
            segment_words = []
            for w in words:
                w_start = w.get("start", 0)
                w_end = w.get("end", 0)
                if w_start >= seg_start and w_end <= seg_end:
                    segment_words.append(w)

            if segment_words:
                # Build readable segment with timestamps every ~10 words
                lines = []
                current_line_words = []
                last_ts = None
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
                    word_text = w.get("punctuated_word", w.get("word", ""))
                    current_line_words.append(word_text)

                if current_line_words:
                    lines.append(" ".join(current_line_words))

                segment = "\n".join(lines)
                if len(segment) > 100:
                    return segment

        # Method 2: Line-based extraction from labeled transcript
        pattern = re.compile(r'\[(\d+):(\d+\.?\d*)\]')
        transcript_lines = labeled_transcript.split("\n")
        segment_lines = []

        for line in transcript_lines:
            match = pattern.search(line)
            if match:
                mm = float(match.group(1))
                ss = float(match.group(2))
                line_ts = mm * 60 + ss
                if seg_start <= line_ts <= seg_end:
                    segment_lines.append(line)

        if segment_lines:
            return "\n".join(segment_lines)

        # Final fallback
        return labeled_transcript[:3000]

    except Exception as e:
        print(f"[S06] Error extracting segment for candidate {candidate.get('candidate_id')}: {e}")
        return labeled_transcript[:3000]


def _evaluate_batch(
    batch_data: list,
    channel_context: str
) -> list:
    """
    Sends a batch of candidates to Gemini for evaluation.
    Returns list of evaluated candidates.
    """
    prompt = PROMPT
    prompt = prompt.replace("CHANNEL_CONTEXT_PLACEHOLDER", channel_context)
    prompt = prompt.replace("BATCH_CANDIDATES_PLACEHOLDER", json.dumps(batch_data, indent=2))

    result = generate_json(prompt, model=settings.GEMINI_MODEL_PRO)

    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    elif isinstance(result, dict):
        # Handle case where Gemini wraps in an object
        candidates = result.get("candidates") or result.get("evaluated") or []
        return [item for item in candidates if isinstance(item, dict)]

    return []


def _evaluate_single(
    candidate_data: dict,
    channel_context: str
) -> Optional[dict]:
    """
    Evaluates a single candidate individually (retry for missed batch items).
    """
    try:
        result = _evaluate_batch([candidate_data], channel_context)
        if result:
            return result[0]
        return None
    except Exception as e:
        print(f"[S06] Single retry failed for candidate {candidate_data.get('candidate_id')}: {e}")
        return None


def run(
    candidates: list,
    labeled_transcript: str,
    transcript_data: dict,
    channel_dna: dict,
    channel_id: str,
    job_id: str
) -> list:
    """
    S06: Batch Evaluation
    Evaluates S05 candidates in batches using transcript segments.
    Returns filtered, sorted list of clips ready for precision cutting.
    """
    print(f"[S06] Starting batch evaluation for job {job_id} with {len(candidates)} candidates")

    if not candidates:
        print("[S06] No candidates to evaluate. Returning empty list.")
        return []

    try:
        # 1. Build channel context (same function as S05 for consistency)
        channel_context = build_channel_context(channel_dna, channel_id)

        # 2. Prepare batch data — extract transcript segments for each candidate
        all_batch_data = []
        for candidate in candidates:
            segment = _extract_transcript_segment(
                candidate, labeled_transcript, transcript_data
            )
            batch_item = {
                "candidate_id": candidate.get("candidate_id"),
                "timestamp": candidate.get("timestamp", "00:00"),
                "hook_text": candidate.get("hook_text", ""),
                "reason": candidate.get("reason", ""),
                "primary_signal": candidate.get("primary_signal", ""),
                "strength": candidate.get("strength", 0),
                "content_type": candidate.get("content_type", ""),
                "recommended_start": candidate.get("recommended_start", 0),
                "recommended_end": candidate.get("recommended_end", 0),
                "transcript_segment": segment
            }
            all_batch_data.append(batch_item)

        # 3. Process in batches of 6
        batch_size = 6
        all_evaluated = []

        for i in range(0, len(all_batch_data), batch_size):
            batch = all_batch_data[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(all_batch_data) + batch_size - 1) // batch_size

            print(f"[S06] Processing batch {batch_num}/{total_batches} ({len(batch)} candidates)")

            try:
                evaluated = _evaluate_batch(batch, channel_context)

                # Track which candidates were returned
                returned_ids = {str(item.get("candidate_id", "")) for item in evaluated}
                sent_ids = {str(item.get("candidate_id", "")) for item in batch}
                missing_ids = sent_ids - returned_ids

                all_evaluated.extend(evaluated)

                # 4. Retry missing candidates individually
                if missing_ids:
                    print(f"[S06] Batch {batch_num}: Gemini skipped {len(missing_ids)} candidates: {missing_ids}")
                    for missing_id in missing_ids:
                        missing_item = next(
                            (item for item in batch if str(item.get("candidate_id")) == missing_id),
                            None
                        )
                        if missing_item:
                            retry_result = _evaluate_single(missing_item, channel_context)
                            if retry_result:
                                all_evaluated.append(retry_result)
                                print(f"[S06] Recovered candidate {missing_id} via individual retry")
                            else:
                                print(f"[S06] Failed to recover candidate {missing_id}")

            except Exception as batch_err:
                print(f"[S06] Batch {batch_num} failed: {batch_err}")
                # Fallback: try each candidate individually
                print(f"[S06] Falling back to individual evaluation for batch {batch_num}")
                for item in batch:
                    try:
                        single_result = _evaluate_single(item, channel_context)
                        if single_result:
                            all_evaluated.append(single_result)
                    except Exception as single_err:
                        print(f"[S06] Individual eval failed for candidate {item.get('candidate_id')}: {single_err}")

        print(f"[S06] Total evaluated: {len(all_evaluated)}")

        # 5. Log quality gate results (keep ALL clips — failed ones get cut too for manual review)
        passed_count = 0
        failed_count = 0
        for clip in all_evaluated:
            verdict = clip.get("quality_verdict", "fail")
            if verdict in ("pass", "fixable"):
                passed_count += 1
            else:
                failed_count += 1
                cid = clip.get("candidate_id", "?")
                reason = clip.get("reject_reason", "no reason given")
                print(f"[S06] Candidate {cid} failed quality gate: {reason}")

        print(f"[S06] Quality gate: {passed_count} passed, {failed_count} failed, {len(all_evaluated)} total proceeding")

        if not all_evaluated:
            print("[S06] No candidates evaluated. Returning empty list.")
            return []

        # 6. Sort: passed clips first (by posting_order), then failed clips at the end
        def sort_key(clip):
            is_failed = 0 if clip.get("quality_verdict", "fail") in ("pass", "fixable") else 1
            return (is_failed, clip.get("posting_order", 999))

        all_evaluated.sort(key=sort_key)

        # 7. Assign posting_order only to passed clips (failed clips keep 999)
        order = 1
        for clip in all_evaluated:
            if clip.get("quality_verdict", "fail") in ("pass", "fixable"):
                if clip.get("posting_order") is None or clip.get("posting_order") == 999:
                    clip["posting_order"] = order
                    order += 1

        print(f"[S06] Final output: {len(all_evaluated)} clips ({passed_count} passed, {failed_count} failed)")
        try:
            pass_count = sum(1 for c in all_evaluated if c.get("quality_verdict") == "pass")
            fail_count = len(all_evaluated) - pass_count
            director_events.emit_sync(
                module="module_1", event="s06_evaluation_completed",
                payload={"job_id": job_id, "pass_count": pass_count, "fail_count": fail_count},
                channel_id=channel_id,
            )
        except Exception:
            pass
        return all_evaluated

    except Exception as e:
        print(f"[S06] Critical error: {e}")
        import traceback
        traceback.print_exc()
        return []
