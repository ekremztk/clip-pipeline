import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.config import settings
from app.pipeline.json_parser import parse_json_object_response
from app.services.claude_client import call_claude
from app.services.supabase_client import get_client
from app.pipeline.prompts.unified_discovery import (
    PROMPT,
    TARGET_GUEST_BLOCK,
    SCENE_BOUNDARY_BLOCK,
)


def build_channel_context(channel_dna: dict, channel_id: str) -> str:
    """
    Produce the channel instructions the model reads.

    When `channel_dna.prompt_text` is set it is passed through verbatim: what the
    owner writes is exactly what the model sees. Reassembling the prompt from a
    dozen structured fields on every call meant nobody could read the result, and
    the DNA editor silently dropped any field it did not know about.

    Only `duration_range` and `keyterms` still need to be structured, because
    code reads them (S05/S06/S07 limits, and S02's Deepgram hints). Everything
    else belongs in prose.

    The field-by-field rendering below stays as the fallback for channels that
    have not been migrated.
    """
    prompt_text = (channel_dna or {}).get("prompt_text")
    if isinstance(prompt_text, str) and prompt_text.strip():
        memory = _get_channel_memory(channel_id)
        if memory:
            return f"{prompt_text.strip()}\n\nCHANNEL PERFORMANCE HISTORY:\n{memory}"
        return prompt_text.strip()

    if not channel_dna:
        return (
            "No channel-specific data available yet. Use general viral content principles:\n"
            "PRIORITIZE: Strong hooks, emotional moments, controversial opinions, humor, complete story arcs.\n"
            "NEVER SELECT: Clips that need external context, mid-sentence cuts, low-energy monologues.\n"
            "PREFERRED CONTENT TYPES: revelation, debate, humor, emotional, controversial, storytelling"
        )

    lines = []

    # 1. Channel identity
    audience = channel_dna.get("audience_identity", "")
    tone = channel_dna.get("tone", "")
    if audience or tone:
        identity = "YOU ARE EDITING FOR:"
        if audience:
            identity += f" {audience}"
        if tone:
            identity += f"\nTONE: {tone}"
        lines.append(identity)

    # 2. What to prioritize (do_list)
    do_list = channel_dna.get("do_list", [])
    if do_list:
        lines.append("\nPRIORITIZE THESE MOMENTS (ranked by importance):")
        for i, item in enumerate(do_list, 1):
            lines.append(f"  {i}. {item}")

    # 3. What to never select (dont_list)
    dont_list = channel_dna.get("dont_list", [])
    if dont_list:
        lines.append("\nNEVER SELECT:")
        for item in dont_list:
            lines.append(f"  - {item}")

    # 4. Forbidden topics (no_go_zones)
    no_go = channel_dna.get("no_go_zones", [])
    if no_go:
        lines.append(f"\nFORBIDDEN TOPICS (hard exclusion): {', '.join(no_go)}")
    else:
        lines.append("\nFORBIDDEN TOPICS: None specified.")

    # 5. Content types
    content_types = channel_dna.get("best_content_types", [])
    if content_types:
        lines.append(f"\nPREFERRED CONTENT TYPES: {', '.join(content_types)}")
    else:
        lines.append("\nPREFERRED CONTENT TYPES: revelation, debate, humor, emotional, controversial, storytelling")

    # 6. Humor profile
    humor = channel_dna.get("humor_profile", {})
    if humor:
        style = humor.get("style", "general")
        freq = humor.get("frequency", "occasional")
        triggers = humor.get("triggers", [])
        humor_line = f"\nHUMOR STYLE: {style}. Frequency: {freq}."
        if triggers:
            humor_line += f" Triggers: {', '.join(triggers)}."
        if style == "none" or freq == "none":
            humor_line += " Humor is NOT a priority for this channel — do not force funny moments."
        lines.append(humor_line)

    # 7. Duration preference
    duration_range = channel_dna.get("duration_range", {})
    avg_dur = channel_dna.get("avg_successful_duration")
    if duration_range or avg_dur:
        dur_line = "\nDURATION PREFERENCE:"
        if avg_dur:
            dur_line += f" Average successful clip is {avg_dur}s."
        if duration_range:
            dur_min = duration_range.get("min", "")
            dur_max = duration_range.get("max", "")
            if dur_min and dur_max:
                dur_line += f" Sweet spot: {dur_min}-{dur_max}s."
        lines.append(dur_line)

    # 8. Speaker preference
    speaker_pref = channel_dna.get("speaker_preference", "")
    if speaker_pref:
        lines.append(f"\nSPEAKER PREFERENCE: {speaker_pref}")

    # 9. Hook style
    hook_style = channel_dna.get("hook_style", "")
    if hook_style:
        lines.append(f"BEST HOOK STYLE: {hook_style}")

    # 10. Sacred topics (high value)
    sacred = channel_dna.get("sacred_topics", [])
    if sacred:
        lines.append(f"\nHIGH-VALUE TOPICS (audience cares deeply): {', '.join(sacred)}")

    # 10b. Free-form note from the channel owner — anything the structured
    # fields above can't express (measured findings, standing caveats).
    selection_note = channel_dna.get("selection_note", "")
    if selection_note:
        lines.append(f"\nWHAT THIS CHANNEL HAS LEARNED: {selection_note}")

    # 11. YouTube title/description style
    title_style = channel_dna.get("title_style", "")
    if title_style:
        lines.append(f"\nYOUTUBE TITLE STYLE: {title_style}")

    description_template = channel_dna.get("description_template", "")
    if description_template:
        lines.append(f"YOUTUBE DESCRIPTION TEMPLATE: {description_template}")

    # 12. Channel memory context
    channel_memory = _get_channel_memory(channel_id)
    if channel_memory:
        lines.append(f"\nCHANNEL PERFORMANCE HISTORY:\n{channel_memory}")

    return "\n".join(lines)


def _get_channel_memory(channel_id: str) -> str:
    """
    Retrieves recent clip performance stats for the channel.
    Lightweight version — just key stats, no heavy queries.
    """
    try:
        if not channel_id:
            return ""

        supabase = get_client()
        ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()

        response = (
            supabase.table("clips")
            .select("content_type, is_successful, duration_s")
            .eq("channel_id", channel_id)
            .gte("created_at", ninety_days_ago)
            .execute()
        )

        clips = response.data
        if not clips or len(clips) < 3:
            return ""

        # Nothing is labelled, so there is no performance history to report —
        # only a count of rows, most of which were rejected and never published.
        # Saying "156 clips produced, 0 successful, 0 failed" told the model
        # nothing true and cost tokens in both S05 and S06. Until is_successful
        # is actually populated, stay silent.
        if not any(c.get("is_successful") is not None for c in clips):
            return ""

        total = len(clips)
        successful = [c for c in clips if c.get("is_successful")]
        failed = [c for c in clips if c.get("is_successful") is False]

        lines = [f"Last 90 days: {total} clips produced, {len(successful)} successful, {len(failed)} failed."]

        if successful:
            type_counts = {}
            for c in successful:
                ct = c.get("content_type", "unknown")
                type_counts[ct] = type_counts.get(ct, 0) + 1
            sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
            top_types = [f"{t[0]} ({t[1]})" for t in sorted_types[:3]]
            lines.append(f"Best performing types: {', '.join(top_types)}")

        if failed:
            fail_counts = {}
            for c in failed:
                ct = c.get("content_type", "unknown")
                fail_counts[ct] = fail_counts.get(ct, 0) + 1
            sorted_fails = sorted(fail_counts.items(), key=lambda x: x[1], reverse=True)
            worst_types = [f"{t[0]} ({t[1]})" for t in sorted_fails[:3]]
            lines.append(f"Underperforming types: {', '.join(worst_types)}")

        return "\n".join(lines)

    except Exception as e:
        print(f"[S05] Error getting channel memory: {e}")
        return ""


def _validate_and_repair_candidates(
    raw_candidates: list,
    utterance_index: dict,
    words: list,
    video_duration_s: float,
    min_duration: int,
    max_duration: int,
    scene_ranges: Optional[list] = None,
) -> list:
    """
    Resolve utterance ids to seconds and enforce the mechanical invariants.

    Everything checked here is verifiable against the transcript — the ids exist,
    start precedes end, the window fits the video and the duration limits. No
    judgement about content is made or reversed at this layer.
    """
    valid = []
    for i, c in enumerate(raw_candidates):
        if not isinstance(c, dict):
            print(f"[S05-Validate] Dropped item {i}: not a dict ({type(c).__name__})")
            continue

        cid = c.get("candidate_id", "?")

        # Boundaries arrive as utterance ids and are resolved here. An id that
        # is not in the transcript is a hallucination, not a rounding error, so
        # the candidate is dropped rather than repaired.
        start_id = str(c.get("start_utterance_id", "")).strip()
        end_id = str(c.get("end_utterance_id", "")).strip()
        start_span = utterance_index.get(start_id)
        end_span = utterance_index.get(end_id)

        if not start_span or not end_span:
            bad = [x for x, span in ((start_id, start_span), (end_id, end_span)) if not span]
            print(f"[S05-Validate] Dropped candidate {cid}: unknown utterance id(s) {bad}")
            continue

        start = start_span[0]
        end = end_span[1]

        # The id fixes the window; the model's own quotes place the cut inside it.
        refined_start = refine_boundary_by_text(words, start_span, c.get("hook_text", ""), "start")
        if refined_start is not None and start_span[0] <= refined_start < start_span[1]:
            start = refined_start
        refined_end = refine_boundary_by_text(words, end_span, c.get("end_text", ""), "end")
        if refined_end is not None and end_span[0] < refined_end <= end_span[1]:
            end = refined_end

        c["recommended_start"] = start
        c["recommended_end"] = end

        if not str(c.get("hook_text", "")).strip():
            print(f"[S05-Validate] Warning: candidate {cid} has empty hook_text")
        if not str(c.get("content_type", "")).strip():
            c["content_type"] = "unknown"

        if start < 0:
            start = 0.0
            c["recommended_start"] = start
        if end <= start:
            print(f"[S05-Validate] Dropped candidate {cid}: end ({end}) <= start ({start})")
            continue
        if video_duration_s > 0 and start >= video_duration_s:
            print(f"[S05-Validate] Dropped candidate {cid}: start ({start:.1f}) >= video ({video_duration_s:.1f})")
            continue
        if video_duration_s > 0 and end > video_duration_s:
            end = video_duration_s
            c["recommended_end"] = end

        dur = end - start
        if dur < min_duration:
            print(f"[S05-Validate] Dropped candidate {cid}: duration {dur:.1f}s < min {min_duration}s")
            continue
        if dur > max_duration:
            print(f"[S05-Validate] Dropped candidate {cid}: duration {dur:.1f}s > max {max_duration}s")
            continue

        # Scene boundary guard: clip MUST fit inside a single scene.
        # Source video has hard cuts between scenes — spanning them would
        # stitch unrelated audio together.
        if scene_ranges:
            inside = False
            for s_start, s_end in scene_ranges:
                if start >= s_start and end <= s_end:
                    inside = True
                    break
            if not inside:
                print(
                    f"[S05-Validate] Dropped candidate {cid}: "
                    f"[{start:.1f}s-{end:.1f}s] crosses scene boundary"
                )
                continue

        # Clamp & record target_guest_dominance (0.0-1.0).
        tgd = c.get("target_guest_dominance")
        if tgd is not None:
            try:
                c["target_guest_dominance"] = max(0.0, min(1.0, float(tgd)))
            except (ValueError, TypeError):
                c["target_guest_dominance"] = None

        valid.append(c)
    return valid


def _parse_claude_json(raw_text: str) -> dict:
    """Safely parses Claude's JSON response into {timeline_map, candidates}."""
    return parse_json_object_response(raw_text, log_prefix="[S05]")


def build_utterance_index(transcript_data: dict) -> dict:
    """
    Map every `U####` id to its (start, end) seconds.

    Numbering has to match s04 exactly: it enumerates the raw utterance list
    from 1 and keeps that number even for utterances it later drops, so
    U0042 is always utterances[41] whether or not the scene filter ran.
    """
    index = {}
    for seq, utt in enumerate(transcript_data.get("utterances", []) or [], start=1):
        try:
            start = float(utt.get("start", 0.0))
            end = float(utt.get("end", start))
        except (TypeError, ValueError):
            continue
        index[f"U{seq:04d}"] = (start, end)
    return index


def _normalize(text: str) -> list:
    return [w for w in re.sub(r"[^\w\s']", " ", (text or "").lower()).split() if w]


def refine_boundary_by_text(
    words: list, span: tuple, quote: str, mode: str
) -> Optional[float]:
    """
    Move a boundary to where a quoted phrase actually begins or ends.

    Utterance ids give a reliable coarse window but cannot address a point
    inside an utterance, and Deepgram routinely packs the filler and the hook
    into one — "But, you know, we're always on chats, and the only one that is
    not really good…" is a single utterance whose good opening starts 2.3s in.
    The model already quotes the exact first and last words it wants, so those
    quotes are used to find the point the id cannot express.

    Returns None when the quote isn't found, leaving the id boundary intact.
    """
    needle = _normalize(quote)
    if not needle or not words:
        return None

    start_s, end_s = span
    window = [
        w for w in words
        if w.get("start") is not None and start_s - 0.25 <= w["start"] <= end_s + 0.25
    ]
    if len(window) < len(needle):
        return None

    hay = [_normalize(w.get("punctuated_word") or w.get("word") or "") for w in window]
    hay = [h[0] if h else "" for h in hay]

    for i in range(len(hay) - len(needle) + 1):
        if hay[i:i + len(needle)] == needle:
            return window[i]["start"] if mode == "start" else window[i + len(needle) - 1]["end"]

    # Partial match on the leading/trailing few words is enough to place a cut.
    probe = needle[:4] if mode == "start" else needle[-4:]
    if len(probe) >= 2:
        for i in range(len(hay) - len(probe) + 1):
            if hay[i:i + len(probe)] == probe:
                return window[i]["start"] if mode == "start" else window[i + len(probe) - 1]["end"]
    return None


def audit_timeline_coverage(timeline_map: list, index: dict) -> dict:
    """
    Check the model's own map against the episode it was given.

    This is the point of asking for a map at all: a model that stopped reading
    partway through cannot describe the part it skipped. Gaps here are the
    signal that discovery ran short, which is otherwise invisible — the Sofia
    source returned four candidates that all sat inside the first 41% of the
    video and nothing reported it.
    """
    if not index:
        return {"covered_pct": 0.0, "gaps": []}

    total_end = max(e for _, e in index.values())
    spans = []
    for entry in timeline_map or []:
        if not isinstance(entry, dict):
            continue
        a = index.get(str(entry.get("from_utterance_id", "")).strip())
        b = index.get(str(entry.get("to_utterance_id", "")).strip())
        if a and b and b[1] > a[0]:
            spans.append((a[0], b[1]))

    spans.sort()
    covered, gaps, cursor = 0.0, [], 0.0
    for start, end in spans:
        if start > cursor + 1.0:
            gaps.append((round(cursor, 1), round(start, 1)))
        covered += max(0.0, end - max(start, cursor))
        cursor = max(cursor, end)
    if total_end > cursor + 1.0:
        gaps.append((round(cursor, 1), round(total_end, 1)))

    return {
        "covered_pct": round(covered / total_end * 100, 1) if total_end else 0.0,
        "gaps": gaps,
    }


def run(
    video_path: str,
    labeled_transcript: str,
    channel_dna: dict,
    channel_id: str,
    video_duration_s: float,
    job_id: str,
    transcript_data: Optional[dict] = None,
    audio_path: Optional[str] = None,
    clip_duration_min: Optional[int] = None,
    clip_duration_max: Optional[int] = None,
    target_guest: Optional[str] = None,
    scene_filter_active: bool = False,
    scene_ranges: Optional[list] = None,
    allow_premium: bool = False,
) -> list:
    """
    S05: Unified Discovery — one Claude call over the full transcript.

    The model returns a timeline map plus candidates whose boundaries are
    utterance ids; this function resolves those ids to seconds. It is never
    asked for a timestamp, because the arithmetic competes with the judgement
    and the arithmetic used to win.

    `transcript_data` supplies the utterances the ids resolve against and is
    required — without it there is nothing to resolve and the step returns [].
    """
    print(f"[S05] Starting unified discovery for job {job_id}")

    try:
        # 0. Index the utterances the model's ids will resolve against.
        utterance_index = build_utterance_index(transcript_data or {})
        if not utterance_index:
            print("[S05] No utterances to resolve ids against — cannot run discovery")
            return []
        print(f"[S05] Utterance index: {len(utterance_index)} ids")

        # 1. Build channel context (DNA → natural language)
        channel_context = build_channel_context(channel_dna, channel_id)
        print(f"[S05] Channel context built ({len(channel_context)} chars)")

        # 2. Duration limits — job-level override > channel DNA > config defaults
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

        # Soft guidance — Claude can return fewer if content is weak
        if video_duration_s < 300:       # < 5 min
            max_candidates = 4
        elif video_duration_s < 1200:    # 5–20 min
            max_candidates = 8
        else:                            # 20+ min
            max_candidates = 12

        print(
            f"[S05] Duration: {min_duration}s–{max_duration}s "
            f"soft candidate guidance: {max_candidates}"
        )

        # 3. Build prompt — full transcript in one shot.
        # Conditional blocks are included only when relevant so the LLM doesn't
        # see "TARGET GUEST: none" style prompts (which cause hallucination of
        # a target from episode context).
        target_block = ""
        if target_guest and target_guest.strip():
            target_block = TARGET_GUEST_BLOCK.replace(
                "TARGET_GUEST_NAME_PLACEHOLDER", target_guest.strip()
            )
        scene_block = SCENE_BOUNDARY_BLOCK if scene_filter_active else ""

        prompt = PROMPT
        prompt = prompt.replace("TARGET_GUEST_BLOCK_PLACEHOLDER", target_block)
        prompt = prompt.replace("SCENE_BOUNDARY_BLOCK_PLACEHOLDER", scene_block)
        prompt = prompt.replace("VIDEO_DURATION_PLACEHOLDER", str(int(video_duration_s)))
        prompt = prompt.replace("MAX_CANDIDATES_PLACEHOLDER", str(max_candidates))
        prompt = prompt.replace("CHANNEL_CONTEXT_PLACEHOLDER", channel_context)
        prompt = prompt.replace("LABELED_TRANSCRIPT_PLACEHOLDER", labeled_transcript)
        prompt = prompt.replace("MIN_DURATION_PLACEHOLDER", str(min_duration))
        prompt = prompt.replace("MAX_DURATION_PLACEHOLDER", str(max_duration))

        print(
            f"[S05] Prompt flags — target_guest={bool(target_guest)}, "
            f"scene_filter={scene_filter_active}"
        )

        # 4. Single Claude call — no chunking, full context
        print(
            f"[S05] Calling Claude ({settings.CLAUDE_MODEL}) — "
            f"transcript: {len(labeled_transcript)} chars"
        )
        content = [{"type": "text", "text": prompt}]
        raw_response = call_claude(
            content=content,
            system=(
                "You are a professional short-form video editor specializing in viral clips. "
                "Return ONLY a valid JSON object. No markdown, no explanation outside the JSON."
            ),
            max_tokens=16000,
            allow_premium=allow_premium,
        )

        payload = _parse_claude_json(raw_response)
        timeline_map = payload.get("timeline_map") or []
        raw_candidates = payload.get("candidates") or []

        # 5. Coverage audit — did discovery actually read to the end?
        coverage = audit_timeline_coverage(timeline_map, utterance_index)
        print(
            f"[S05] Timeline map: {len(timeline_map)} region(s), "
            f"{coverage['covered_pct']}% of the episode covered"
        )
        for gap_start, gap_end in coverage["gaps"]:
            print(f"[S05] COVERAGE GAP: {gap_start}s–{gap_end}s was never mapped")

        print(f"[S05] Claude returned {len(raw_candidates)} raw candidates")
        if not raw_candidates:
            print("[S05] Claude returned no candidates. Returning empty list.")
            return []

        # 6. Resolve utterance ids and enforce mechanical invariants
        valid_candidates = _validate_and_repair_candidates(
            raw_candidates, utterance_index, (transcript_data or {}).get("words") or [],
            video_duration_s, min_duration, max_duration,
            scene_ranges=scene_ranges if scene_filter_active else None,
        )
        print(f"[S05] {len(valid_candidates)} candidates after validation")

        # Reassign sequential candidate_id
        for idx, c in enumerate(valid_candidates, start=1):
            c["candidate_id"] = idx

        return valid_candidates

    except Exception as e:
        # Raise, do not swallow. Returning [] made a crashed model call
        # indistinguishable from a weak source, and the orchestrator would mark
        # the job `completed` with zero clips either way.
        print(f"[S05] Critical error: {e}")
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"S05 discovery failed: {e}") from e
