import json
import re
from typing import Optional

from app.config import settings
from app.pipeline.json_parser import parse_json_list_response
from app.pipeline.prompts.batch_evaluation import SYSTEM_PROMPT, EVALUATION_PROMPT
from app.pipeline.stock_analytics import record_s06_evaluation
from app.pipeline.steps.s05_unified_discovery import build_channel_context
from app.services.claude_client import call_claude


# ── Transcript segment extractor ─────────────────────────────────────────────

def _words_to_natural_text(w_list: list) -> str:
    """
    Render Deepgram word objects as readable lines, one per sentence.

    Each line carries the speaker id as well as the timestamp. Without it these
    snippets were an undifferentiated wall of text, so the model could not tell a
    host question from a guest answer and had to re-derive that by matching the
    snippet back against the labeled transcript in its system context.
    """
    if not w_list:
        return ""

    sentences = []
    current_sentence = []
    sentence_start_ts = None
    sentence_speaker = None

    def flush():
        if not current_sentence or sentence_start_ts is None:
            return
        ts = sentence_start_ts
        label = f"SPEAKER_{chr(ord('A') + sentence_speaker)}" if isinstance(sentence_speaker, int) and 0 <= sentence_speaker < 26 else "SPEAKER_?"
        sentences.append(
            f"[{int(ts // 60):02d}:{ts % 60:05.2f}] {label}: {' '.join(current_sentence)}"
        )

    for w in w_list:
        word_text = w.get("punctuated_word") or w.get("word") or ""
        if not word_text:
            continue

        speaker = w.get("speaker")
        # A speaker change starts a new line even mid-sentence — Deepgram often
        # runs an interjection into the previous speaker's sentence.
        if current_sentence and speaker != sentence_speaker:
            flush()
            current_sentence = []
            sentence_start_ts = None

        if sentence_start_ts is None:
            sentence_start_ts = w.get("start", 0)
            sentence_speaker = speaker

        current_sentence.append(word_text)

        if word_text[-1] in ".!?":
            flush()
            current_sentence = []
            sentence_start_ts = None

    flush()

    return "\n".join(sentences)


def _merge_verdicts_onto_candidates(evaluated: list, candidates: list) -> list:
    """
    Attach each verdict to the candidate it judged.

    Claude returns verdicts, not clips. Its response carries no
    recommended_start/recommended_end at all — boundaries are named only as
    utterance ids, and only when the verdict is `repair` — so treating a
    response object as the clip itself left every approved clip with a 0.0s
    window, and the video-bound clamp downstream then dropped all of them.
    """
    by_id = {str(c.get("candidate_id")): c for c in candidates or []}
    merged = []

    for ev in evaluated or []:
        if not isinstance(ev, dict):
            continue
        cid = str(ev.get("candidate_id", "")).strip()
        original = by_id.get(cid)
        if original is None:
            print(f"[S06] Discarding verdict for unknown candidate {cid or '(missing id)'}")
            continue

        clip = {**original, **ev}
        # A verdict may not move a boundary. The repair path below is the only
        # way boundaries change, and it writes them from resolved utterance ids.
        clip["recommended_start"] = original.get("recommended_start")
        clip["recommended_end"] = original.get("recommended_end")
        clip["start_utterance_id"] = original.get("start_utterance_id")
        clip["end_utterance_id"] = original.get("end_utterance_id")

        _normalise_evaluation_fields(clip)
        merged.append(clip)

    return merged


def _normalise_evaluation_fields(clip: dict) -> None:
    """
    Keep the pre-rewrite field names populated alongside the new ones.

    The evaluation prompt now returns `verdict`, `hallucination_flag` and a
    per-dimension `scores` object; stock_analytics and S08 still read
    `quality_verdict`, `s05_hallucination_flag` and a flat `score`. Writing both
    shapes here keeps one source of truth without a migration in three files.
    """
    verdict = str(clip.get("verdict") or clip.get("quality_verdict") or "").strip().lower()
    if verdict:
        clip["verdict"] = verdict
        clip["quality_verdict"] = verdict

    scores = clip.get("scores")
    if isinstance(scores, dict) and clip.get("score") is None:
        values = []
        for v in scores.values():
            try:
                values.append(float(v))
            except (TypeError, ValueError):
                continue
        if values:
            clip["score"] = int(round(sum(values) / len(values)))

    if clip.get("hallucination_flag") and not clip.get("s05_hallucination_flag"):
        clip["s05_hallucination_flag"] = True


def _mark_omitted(clip: dict, reason: str) -> None:
    clip["verdict"] = "omit"
    clip["quality_verdict"] = "omit"
    clip["omit_reason"] = reason


def _apply_repair(clip: dict, utterance_index: dict, words: list) -> bool:
    """
    Resolve a repair verdict's new boundaries and write them onto the clip.

    Returns False — meaning "this is not a repair" — when the model named no
    boundaries, named ids that do not exist, or named the same window it was
    already given. Only a real, resolvable, different window counts.
    """
    from app.pipeline.steps.s05_unified_discovery import refine_boundary_by_text

    start_id = str(clip.get("repair_start_utterance_id") or "").strip()
    end_id = str(clip.get("repair_end_utterance_id") or "").strip()
    start_span = utterance_index.get(start_id)
    end_span = utterance_index.get(end_id)
    if not start_span or not end_span:
        return False

    new_start, new_end = start_span[0], end_span[1]

    refined = refine_boundary_by_text(words, start_span, clip.get("hook_text", ""), "start")
    if refined is not None and start_span[0] <= refined < start_span[1]:
        new_start = refined
    refined = refine_boundary_by_text(words, end_span, clip.get("end_text", ""), "end")
    if refined is not None and end_span[0] < refined <= end_span[1]:
        new_end = refined

    if new_end <= new_start:
        return False

    old_start = float(clip.get("recommended_start") or 0.0)
    old_end = float(clip.get("recommended_end") or 0.0)
    if abs(new_start - old_start) < 0.25 and abs(new_end - old_end) < 0.25:
        return False

    clip["recommended_start"] = new_start
    clip["recommended_end"] = new_end
    clip["start_utterance_id"] = start_id
    clip["end_utterance_id"] = end_id
    return True


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
        # S04 lines are "[U0042 03:21.85-03:28.97] SPEAKER_A: …". The optional
        # id prefix keeps this working if it is ever handed a bare timestamp.
        pattern = re.compile(r'\[(?:U\d+(?:-U\d+)?\s+)?(\d+):(\d+\.?\d*)')
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

def _build_metadata_context(video_title: str, metadata_subject_name: Optional[str]) -> str:
    title = (video_title or "").strip()
    subject = (metadata_subject_name or "").strip()

    lines = []
    if title:
        lines.append(f"Source video title: {title}")
    else:
        lines.append("Source video title: (not provided)")

    if subject:
        lines.append(f"Explicit metadata subject: {subject}")
        lines.append(
            "Use this exact person as the named subject in suggested_title and suggested_description."
        )
    else:
        lines.append("Explicit metadata subject: (not provided)")
        lines.append(
            "If the source title clearly names the main person, use that name in metadata. "
            "If it does not, do not invent a person name."
        )

    return "\n".join(lines)


def _build_claude_content(
    batch_items: list,
    channel_context: str,
    min_duration: int,
    max_duration: int,
    video_title: str = "",
    metadata_subject_name: Optional[str] = None,
) -> list:
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
            "candidate_id":          cid,
            # Utterance ids, so a repair can be named in the same terms S05 used.
            "start_utterance_id":    item.get("start_utterance_id"),
            "end_utterance_id":      item.get("end_utterance_id"),
            "recommended_start":     item.get("recommended_start"),
            "recommended_end":       item.get("recommended_end"),
            "hook_text":             item.get("hook_text"),
            "end_text":              item.get("end_text"),
            "reason":                item.get("reason"),
            # S05's own read on what a stranger needs. It used to be generated
            # and then dropped before it reached the model that checks exactly
            # that, which is the one place it was worth having.
            "standalone_note":       item.get("standalone_note"),
            "primary_signal":        item.get("primary_signal"),
            "loop_potential":        item.get("loop_potential"),
            "content_type":          item.get("content_type"),
        }
        candidates_text_parts.append(
            f"CANDIDATE {cid}:\n{json.dumps(meta, indent=2)}\n\nTRANSCRIPT:\n{transcript_block}"
        )

    candidates_block = "\n\n---\n\n".join(candidates_text_parts)

    instructions = EVALUATION_PROMPT.replace(
        "CHANNEL_CONTEXT_PLACEHOLDER", channel_context
    ).replace(
        "METADATA_CONTEXT_PLACEHOLDER", _build_metadata_context(video_title, metadata_subject_name)
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
    return parse_json_list_response(raw, log_prefix="[S06]")


# ── Core evaluation logic ─────────────────────────────────────────────────────

def _evaluate_batch_with_claude(
    batch_items: list,
    channel_context: str,
    min_duration: int = 12,
    max_duration: int = 60,
    full_transcript_block: Optional[list] = None,
    video_title: str = "",
    metadata_subject_name: Optional[str] = None,
    allow_premium: bool = False,
) -> list:
    """
    Evaluates a batch of candidates with Claude using transcript only.
    Returns all evaluated candidates (pass + fixable).
    full_transcript_block: optional extra system blocks containing the full labeled transcript.
    """
    print(f"[S06] Claude batch: {len(batch_items)} candidates (text-only)")

    content = _build_claude_content(
        batch_items,
        channel_context,
        min_duration,
        max_duration,
        video_title=video_title,
        metadata_subject_name=metadata_subject_name,
    )
    raw = call_claude(
        content,
        system=SYSTEM_PROMPT,
        extra_system_blocks=full_transcript_block,
        allow_premium=allow_premium,
    )
    return _parse_claude_json(raw)


def _evaluate_single_with_claude(
    item: dict,
    channel_context: str,
    min_duration: int = 12,
    max_duration: int = 60,
    full_transcript_block: Optional[list] = None,
    video_title: str = "",
    metadata_subject_name: Optional[str] = None,
    allow_premium: bool = False,
) -> Optional[dict]:
    try:
        results = _evaluate_batch_with_claude(
            [item],
            channel_context,
            min_duration,
            max_duration,
            full_transcript_block,
            video_title=video_title,
            metadata_subject_name=metadata_subject_name,
            allow_premium=allow_premium,
        )
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
    video_title: str = "",
    metadata_subject_name: Optional[str] = None,
    allow_premium: bool = False,
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
    if metadata_subject_name:
        print(f"[S06] Metadata subject provided: {metadata_subject_name}")

    if not candidates:
        print("[S06] No candidates. Returning empty list.")
        return []

    try:
        from app.pipeline.steps.s05_unified_discovery import build_utterance_index

        # Same index S05 used, so a repair resolves to exactly the same seconds.
        utterance_index = build_utterance_index(transcript_data or {})
        words = (transcript_data or {}).get("words") or []

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
                "end_text":           candidate.get("end_text", ""),
                "reason":             candidate.get("reason", ""),
                "standalone_note":    candidate.get("standalone_note", ""),
                "primary_signal":     candidate.get("primary_signal", ""),
                "loop_potential":     candidate.get("loop_potential", ""),
                "content_type":       candidate.get("content_type", ""),
                "start_utterance_id": candidate.get("start_utterance_id"),
                "end_utterance_id":   candidate.get("end_utterance_id"),
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
                evaluated = _evaluate_batch_with_claude(
                    batch,
                    channel_context,
                    min_duration,
                    max_duration,
                    full_transcript_block,
                    video_title=video_title,
                    metadata_subject_name=metadata_subject_name,
                    allow_premium=allow_premium,
                )

                all_evaluated.extend(evaluated)

                # Only retry if Claude returned ZERO results — that's a failure.
                # Claude should now return pass/fixable/omit for every candidate.
                if len(evaluated) == 0:
                    print(f"[S06] Batch {batch_num}: Claude returned 0 results — retrying candidates individually")
                    for item in batch:
                        retry = _evaluate_single_with_claude(
                            item,
                            channel_context,
                            min_duration,
                            max_duration,
                            full_transcript_block,
                            video_title=video_title,
                            metadata_subject_name=metadata_subject_name,
                    allow_premium=allow_premium,
                        )
                        if retry:
                            all_evaluated.append(retry)
                            print(f"[S06] Recovered candidate {item.get('candidate_id')}")
                else:
                    returned_ids = {str(item.get("candidate_id", "")) for item in evaluated}
                    sent_ids = {str(item.get("candidate_id", "")) for item in batch}
                    missing_ids = sent_ids - returned_ids
                    if missing_ids:
                        print(f"[S06] Batch {batch_num}: {len(missing_ids)} candidates missing from Claude output: {missing_ids}")

            except Exception as batch_err:
                print(f"[S06] Batch {batch_num} failed: {batch_err}. Falling back to individual evaluation.")
                for item in batch:
                    try:
                        single = _evaluate_single_with_claude(
                            item,
                            channel_context,
                            min_duration,
                            max_duration,
                            full_transcript_block,
                            video_title=video_title,
                            metadata_subject_name=metadata_subject_name,
                    allow_premium=allow_premium,
                        )
                        if single:
                            all_evaluated.append(single)
                    except Exception as single_err:
                        print(f"[S06] Individual eval failed for candidate {item.get('candidate_id')}: {single_err}")

        print(f"[S06] Claude evaluated {len(all_evaluated)} total candidates")

        all_evaluated = _merge_verdicts_onto_candidates(all_evaluated, candidates)

        # Log hallucination flags from inspector role
        flagged = [c for c in all_evaluated if c.get("s05_hallucination_flag")]
        if flagged:
            print(f"[S06] Inspector role flagged {len(flagged)} candidates with hook_text hallucination")
            for c in flagged:
                print(f"[S06]   Candidate {c.get('candidate_id')}: {c.get('hook_text', '')[:60]}")

        # Production filter. `repair` only survives if it actually repaired
        # something: the model must name new boundaries, they must resolve, and
        # they must differ from what it was given. The previous version let the
        # whole 55-71 band through untouched, so a verdict that meant "this has a
        # problem" was read by the code as "approved" — two of the four clips in
        # the Sofia job shipped that way.
        passed = []
        omitted = []
        for clip in all_evaluated:
            cid = clip.get("candidate_id", "?")
            verdict = (clip.get("verdict") or clip.get("quality_verdict") or "").lower()
            notes = clip.get("quality_notes", "")

            if clip.get("hallucination_flag") or clip.get("s05_hallucination_flag"):
                _mark_omitted(clip, "hook_text not found in transcript")
                omitted.append(clip)
                print(f"[S06] Omitted candidate {cid}: hallucinated hook_text")
                continue

            if verdict == "pass":
                passed.append(clip)

            elif verdict in ("repair", "fixable"):
                repaired = _apply_repair(clip, utterance_index, words)
                if repaired:
                    print(f"[S06] Repaired candidate {cid}: {notes}")
                    passed.append(clip)
                else:
                    _mark_omitted(clip, "repair verdict without a usable boundary change")
                    omitted.append(clip)
                    print(f"[S06] Omitted candidate {cid}: asked for repair but moved nothing")

            elif verdict == "omit":
                omitted.append(clip)
                reason = clip.get("omit_reason") or notes or ""
                print(f"[S06] Omitted candidate {cid}: {reason}")

            else:
                print(f"[S06] Safety-filtered unexpected verdict for candidate {cid}: '{verdict}'")

        print(f"[S06] Quality gate: {len(passed)} passed, {len(omitted)} omitted, {len(all_evaluated) - len(passed) - len(omitted)} filtered")

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
                    _mark_omitted(clip, "too short after video-bound clamp")
                    continue
                clip["recommended_start"] = round(clip_start, 3)
                clip["recommended_end"] = round(clip_end, 3)
                clamped_passed.append(clip)
            passed = clamped_passed

        if not passed:
            print("[S06] No candidates passed quality gate.")
            record_s06_evaluation(job_id, all_batch_data, all_evaluated, [])
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
        record_s06_evaluation(job_id, all_batch_data, all_evaluated, passed)

        return passed

    except Exception as e:
        # Raise rather than return []. "Nothing passed the quality bar" and
        # "the evaluation crashed" are different outcomes and used to look
        # identical from the outside — both ended as a completed job with no clips.
        print(f"[S06] Critical error: {e}")
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"S06 evaluation failed: {e}") from e
