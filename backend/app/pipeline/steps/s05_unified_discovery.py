from datetime import datetime, timezone, timedelta
from typing import Optional
from app.config import settings
from app.pipeline.json_parser import parse_json_list_response
from app.services.claude_client import call_claude
from app.services.supabase_client import get_client
from app.pipeline.prompts.unified_discovery import (
    PROMPT,
    TARGET_GUEST_BLOCK,
    SCENE_BOUNDARY_BLOCK,
)


def build_channel_context(channel_dna: dict, channel_id: str) -> str:
    """
    Converts Channel DNA JSON into natural language instructions for Claude.
    This is the core of the niche-agnostic design — every channel gets
    a unique context string generated from its DNA.
    """
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
    video_duration_s: float,
    min_duration: int,
    max_duration: int,
    scene_ranges: Optional[list] = None,
) -> list:
    """
    Validates and auto-repairs Claude's JSON output.
    Handles type coercion, negative timestamps, empty hook_text, and duration bounds.
    """
    REQUIRED_FIELDS = {
        "candidate_id": (int, float),
        "recommended_start": (int, float),
        "recommended_end": (int, float),
        "hook_text": str,
        "content_type": str,
    }
    valid = []
    for i, c in enumerate(raw_candidates):
        if not isinstance(c, dict):
            print(f"[S05-Validate] Dropped item {i}: not a dict ({type(c).__name__})")
            continue

        missing = []
        type_errors = []
        for field, expected_type in REQUIRED_FIELDS.items():
            val = c.get(field)
            if val is None:
                missing.append(field)
            elif not isinstance(val, expected_type):
                try:
                    if expected_type in ((int, float),):
                        c[field] = float(val)
                    elif expected_type == str:
                        c[field] = str(val)
                except (ValueError, TypeError):
                    type_errors.append(field)

        if missing:
            print(f"[S05-Validate] Dropped candidate {c.get('candidate_id', '?')}: missing {missing}")
            continue
        if type_errors:
            print(f"[S05-Validate] Dropped candidate {c.get('candidate_id', '?')}: type errors {type_errors}")
            continue

        cid = c.get("candidate_id", "?")
        start = float(c["recommended_start"])
        end = float(c["recommended_end"])

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
        if dur > max_duration * 1.5:
            print(f"[S05-Validate] Dropped candidate {cid}: duration {dur:.1f}s >> max {max_duration}s")
            continue

        if not c.get("hook_text", "").strip():
            print(f"[S05-Validate] Warning: candidate {cid} has empty hook_text")

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


def _parse_claude_json(raw_text: str) -> list:
    """Safely parses Claude's JSON response."""
    return parse_json_list_response(raw_text, log_prefix="[S05]")


def run(
    video_path: str,
    labeled_transcript: str,
    channel_dna: dict,
    channel_id: str,
    video_duration_s: float,
    job_id: str,
    audio_path: Optional[str] = None,
    clip_duration_min: Optional[int] = None,
    clip_duration_max: Optional[int] = None,
    target_guest: Optional[str] = None,
    scene_filter_active: bool = False,
    scene_ranges: Optional[list] = None,
) -> list:
    """
    S05: Unified Discovery — single Claude Opus call over the full transcript.
    No chunking, no segmentation. Claude sees the entire transcript and returns
    only the strongest candidates.
    """
    print(f"[S05] Starting unified discovery for job {job_id}")

    try:
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

        # When user targets short clips (≤60s), allow discovery up to 120s so a great
        # moment isn't missed just because it slightly exceeds the target length.
        discovery_max = 120 if max_duration <= 60 else max_duration

        # Soft guidance — Claude can return fewer if content is weak
        if video_duration_s < 300:       # < 5 min
            max_candidates = 4
        elif video_duration_s < 1200:    # 5–20 min
            max_candidates = 8
        else:                            # 20+ min
            max_candidates = 12

        print(
            f"[S05] Duration: {min_duration}s–{max_duration}s "
            f"(discovery window: {discovery_max}s), "
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
        prompt = prompt.replace("MAX_DURATION_PLACEHOLDER", str(discovery_max))

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
                "Return ONLY a valid JSON array. No markdown, no explanation outside the JSON."
            ),
            max_tokens=16000,
        )

        raw_candidates = _parse_claude_json(raw_response)
        print(f"[S05] Claude returned {len(raw_candidates)} raw candidates")

        if not raw_candidates:
            print("[S05] Claude returned no candidates. Returning empty list.")
            return []

        # 5. Validate and repair
        valid_candidates = _validate_and_repair_candidates(
            raw_candidates, video_duration_s, min_duration, discovery_max,
            scene_ranges=scene_ranges if scene_filter_active else None,
        )
        print(f"[S05] {len(valid_candidates)} candidates after validation")

        # Reassign sequential candidate_id
        for idx, c in enumerate(valid_candidates, start=1):
            c["candidate_id"] = idx

        return valid_candidates

    except Exception as e:
        print(f"[S05] Critical error: {e}")
        import traceback
        traceback.print_exc()
        return []
