import json
import re
from typing import Optional
from app.config import settings
from app.services.gemini_client import generate_json
from app.services.supabase_client import get_client
from app.pipeline.prompts.unified_discovery import PROMPT
from datetime import datetime, timezone, timedelta


def build_channel_context(channel_dna: dict, channel_id: str) -> str:
    """
    Converts Channel DNA JSON into natural language instructions for Gemini.
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

        # Success rate
        lines = [f"Last 90 days: {total} clips produced, {len(successful)} successful, {len(failed)} failed."]

        # Best content types
        if successful:
            type_counts = {}
            for c in successful:
                ct = c.get("content_type", "unknown")
                type_counts[ct] = type_counts.get(ct, 0) + 1
            sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
            top_types = [f"{t[0]} ({t[1]})" for t in sorted_types[:3]]
            lines.append(f"Best performing types: {', '.join(top_types)}")

        # Failed content types to avoid
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


def _get_guest_profile(guest_name: str) -> str:
    """
    Retrieves or generates guest profile. Returns natural language string.
    Uses existing guest_profiles table with 7-day cache.
    """
    try:
        if not guest_name or not guest_name.strip():
            return "No guest information provided."

        supabase = get_client()
        normalized = guest_name.strip().lower()

        # Check cache
        response = (
            supabase.table("guest_profiles")
            .select("*")
            .eq("normalized_name", normalized)
            .execute()
        )

        profile_data = None

        if response.data:
            row = response.data[0]
            expires_at_str = row.get("expires_at")
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    if expires_at > datetime.now(timezone.utc):
                        print(f"[S05] Using cached guest profile for {guest_name}")
                        profile_data = row.get("profile_data", {})
                except Exception:
                    pass

        # Generate new profile if not cached
        if not profile_data:
            print(f"[S05] Generating new guest profile for {guest_name}")
            from app.pipeline.prompts.guest_research import PROMPT as GUEST_PROMPT
            prompt = GUEST_PROMPT.replace("GUEST_NAME_PLACEHOLDER", guest_name)
            try:
                profile_data = generate_json(prompt, model=settings.GEMINI_MODEL_FLASH)

                # Cache it
                expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
                upsert_data = {
                    "normalized_name": normalized,
                    "original_name": guest_name,
                    "profile_data": profile_data,
                    "expires_at": expires_at,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                if response.data:
                    supabase.table("guest_profiles").update(upsert_data).eq(
                        "normalized_name", normalized
                    ).execute()
                else:
                    supabase.table("guest_profiles").insert(upsert_data).execute()
            except Exception as e:
                print(f"[S05] Guest research failed: {e}")
                return f"Guest: {guest_name} (no additional info available)"

        # Convert profile JSON to natural language
        if isinstance(profile_data, dict):
            parts = [f"GUEST: {guest_name}"]
            summary = profile_data.get("profile_summary", "")
            if summary:
                parts.append(f"Who: {summary}")
            recent = profile_data.get("recent_topics", [])
            if recent:
                parts.append(f"Recent news: {', '.join(recent)}")
            controversies = profile_data.get("controversies", [])
            if controversies:
                parts.append(f"Controversial topics: {', '.join(controversies)}")
            viral = profile_data.get("viral_moments", [])
            if viral:
                parts.append(f"Known viral moments: {', '.join(viral)}")
            clip_note = profile_data.get("clip_potential_note", "")
            if clip_note:
                parts.append(f"Clip potential: {clip_note}")
            return "\n".join(parts)

        return f"Guest: {guest_name}"

    except Exception as e:
        print(f"[S05] Error getting guest profile: {e}")
        return f"Guest: {guest_name} (profile lookup failed)"


def _validate_candidates(
    candidates: list,
    video_duration_s: float,
    min_duration: int,
    max_duration: int,
) -> list:
    """Filters out candidates with invalid timestamps or out-of-range durations."""
    valid = []
    for c in candidates:
        if not isinstance(c, dict) or "candidate_id" not in c:
            continue
        start = float(c.get("recommended_start", 0) or 0)
        end = float(c.get("recommended_end", 0) or 0)
        cid = c.get("candidate_id")
        if start < 0:
            print(f"[S05] Dropped candidate {cid}: negative start {start:.1f}s")
            continue
        if end < 0:
            print(f"[S05] Dropped candidate {cid}: negative end {end:.1f}s")
            continue
        if video_duration_s > 0 and start >= video_duration_s:
            print(f"[S05] Dropped candidate {cid}: start {start:.1f}s >= video duration {video_duration_s:.1f}s")
            continue
        if end <= start:
            print(f"[S05] Dropped candidate {cid}: end {end:.1f}s <= start {start:.1f}s")
            continue
        duration = end - start
        if duration < min_duration:
            print(f"[S05] Dropped candidate {cid}: duration {duration:.1f}s < min {min_duration}s")
            continue
        if duration > max_duration:
            print(f"[S05] Dropped candidate {cid}: duration {duration:.1f}s > max {max_duration}s")
            continue
        valid.append(c)
    return valid


def _calculate_max_candidates(duration_s: float) -> int:
    """Returns max candidate count based on video duration.
    Short videos get tighter limits — too many candidates on short content
    causes Gemini to generate overlapping/duplicate clips covering the same range.
    """
    if duration_s < 300:       # < 5 min
        return 5
    elif duration_s < 900:     # 5–15 min
        return 10
    elif duration_s < 1800:    # 15–30 min
        return 18
    elif duration_s < 3600:    # 30–60 min
        return 25
    else:                      # 60+ min
        return 35


def _segment_transcript(labeled_transcript: str, video_duration_s: float) -> list:
    """
    Uses Gemini Flash to find topic change points in the labeled transcript.
    Returns a list of dicts: {"topic": str, "start": float, "end": float}

    Rules:
    - Min segment: 8 min (480s), max: 20 min (1200s)
    - Segments that exceed 20min are time-split
    - 2-minute overlap added between segments so boundary candidates aren't lost
    - Falls back to equal 15-min chunks on failure or for videos < 20min
    """
    MIN_SEG = 480.0
    MAX_SEG = 1200.0
    OVERLAP = 120.0

    # Skip segmentation for short videos
    if video_duration_s < MIN_SEG:
        return [{"topic": "full_video", "start": 0.0, "end": video_duration_s}]

    try:
        from app.services.gemini_client import generate
        prompt = (
            "You are a podcast topic analyzer. Read the labeled transcript below and identify topic change points.\n\n"
            "Return a JSON array of topic segments. Each segment: {\"topic\": \"short description\", \"start\": float, \"end\": float}\n"
            "Rules:\n"
            f"- Video duration: {video_duration_s:.0f}s\n"
            "- Minimum segment length: 480 seconds\n"
            "- Maximum segment length: 1200 seconds\n"
            "- Cover the entire video from start to end with no gaps\n"
            "- Return ONLY the JSON array, no markdown\n\n"
            "TRANSCRIPT:\n" + labeled_transcript[:40000]
        )
        raw = generate(prompt, model=settings.GEMINI_MODEL_FLASH)
        if raw:
            cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            segs = json.loads(cleaned)
            if isinstance(segs, list) and all(isinstance(s, dict) for s in segs):
                # Apply max segment safety split and add overlaps
                final_segs = []
                for seg in segs:
                    s = float(seg.get("start", 0))
                    e = float(seg.get("end", 0))
                    topic = seg.get("topic", "segment")
                    while e - s > MAX_SEG:
                        mid = s + MAX_SEG
                        final_segs.append({"topic": topic, "start": s, "end": mid + OVERLAP})
                        s = mid
                    final_segs.append({"topic": topic, "start": s, "end": e})
                # Add overlaps between segments
                overlapped = []
                for i, seg in enumerate(final_segs):
                    s = max(0.0, seg["start"] - (OVERLAP if i > 0 else 0))
                    e = min(video_duration_s, seg["end"] + (OVERLAP if i < len(final_segs) - 1 else 0))
                    overlapped.append({"topic": seg["topic"], "start": s, "end": e})
                print(f"[S05] Topic segmentation: {len(overlapped)} segments")
                return overlapped
    except Exception as e:
        print(f"[S05] Topic segmentation failed: {e}. Falling back to equal 15-min chunks.")

    # Fallback: equal 15-min chunks with 2-min overlap
    chunk = 900.0
    segs = []
    s = 0.0
    while s < video_duration_s:
        e = min(video_duration_s, s + chunk)
        segs.append({"topic": "segment", "start": max(0.0, s - OVERLAP), "end": min(video_duration_s, e + OVERLAP)})
        s = e
    return segs


def _validate_and_repair_candidates(
    raw_candidates: list,
    video_duration_s: float,
    min_duration: int,
    max_duration: int,
) -> list:
    """
    Validates and auto-repairs Gemini's JSON output.
    Handles type coercion, negative timestamps, empty hook_text, and duration bounds.
    Replaces the simpler _validate_candidates() for full validation.
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

        # Coerce required fields
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

        valid.append(c)
    return valid


def _extract_segment_transcript(labeled_transcript: str, seg_start: float, seg_end: float) -> str:
    """
    Extracts labeled transcript lines that fall within [seg_start, seg_end].
    Uses the [MM:SS.ss] timestamps in the labeled transcript.
    """
    pattern = re.compile(r'\[(\d+):(\d+\.?\d*)\]')
    lines = labeled_transcript.split("\n")
    result = []
    for line in lines:
        m = pattern.search(line)
        if m:
            ts = float(m.group(1)) * 60 + float(m.group(2))
            if seg_start <= ts <= seg_end:
                result.append(line)
        elif not result:
            continue  # skip header lines before first in-range line
    return "\n".join(result)


def _parse_gemini_json(raw_text: str) -> list:
    """
    Safely parses Gemini's JSON response.
    Handles the chronic LLM issue of wrapping output in ```json``` markers.
    """
    if not raw_text:
        return []

    cleaned = raw_text.strip()

    # Strip markdown wrappers (Gemini's chronic habit)
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    cleaned = cleaned.strip()

    # Remove control characters
    cleaned = re.sub(r'[\x00-\x1f\x7f]', '', cleaned)

    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and "candidates" in result:
            return result["candidates"]
        else:
            print(f"[S05] Unexpected JSON structure: {type(result)}")
            return []
    except json.JSONDecodeError as e:
        print(f"[S05] JSON parse error: {e}")
        print(f"[S05] Raw snippet: {cleaned[:300]}")
        return []


def run(
    video_path: str,
    labeled_transcript: str,
    channel_dna: dict,
    guest_name: Optional[str],
    channel_id: str,
    video_duration_s: float,
    job_id: str,
    audio_path: Optional[str] = None,
    clip_duration_min: Optional[int] = None,
    clip_duration_max: Optional[int] = None,
) -> list:
    """
    S05: Unified Discovery (Transcript-Only)
    Uses labeled transcript + channel context + guest profile to find clip candidates.
    Video/audio analysis is NOT done here — S06 handles visual verification with frames.

    clip_duration_min / clip_duration_max: job-level user selection (highest priority).
    Falls back to channel DNA, then to config defaults.
    """
    print(f"[S05] Starting unified discovery for job {job_id}")

    try:
        # 1. Build channel context (DNA → natural language)
        channel_context = build_channel_context(channel_dna, channel_id)
        print(f"[S05] Channel context built ({len(channel_context)} chars)")

        # 2. Get guest profile
        guest_profile_text = _get_guest_profile(guest_name)
        print(f"[S05] Guest profile: {guest_profile_text[:100]}...")

        # 3. Calculate limits — job-level override > channel DNA > config
        max_candidates = _calculate_max_candidates(video_duration_s)
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
        print(f"[S05] Duration limits: {min_duration}s–{max_duration}s (job_override={'yes' if clip_duration_min is not None else 'no'})")

        # 4. Build prompt
        prompt = PROMPT
        prompt = prompt.replace("VIDEO_DURATION_PLACEHOLDER", str(int(video_duration_s)))
        prompt = prompt.replace("MAX_CANDIDATES_PLACEHOLDER", str(max_candidates))
        prompt = prompt.replace("CHANNEL_CONTEXT_PLACEHOLDER", channel_context)
        prompt = prompt.replace("GUEST_PROFILE_PLACEHOLDER", guest_profile_text)
        prompt = prompt.replace("LABELED_TRANSCRIPT_PLACEHOLDER", labeled_transcript)
        prompt = prompt.replace("MIN_DURATION_PLACEHOLDER", str(min_duration))
        prompt = prompt.replace("MAX_DURATION_PLACEHOLDER", str(max_duration))

        # 5. Topic segmentation — splits long videos into overlapping chunks
        segments = _segment_transcript(labeled_transcript, video_duration_s)
        print(f"[S05] Discovery will run over {len(segments)} segment(s)")

        all_raw_candidates = []

        for seg_idx, segment in enumerate(segments):
            seg_start = segment["start"]
            seg_end = segment["end"]
            seg_topic = segment["topic"]
            print(f"[S05] Segment {seg_idx+1}/{len(segments)}: '{seg_topic}' ({seg_start:.0f}s–{seg_end:.0f}s)")

            # Extract transcript lines for this segment
            seg_transcript = _extract_segment_transcript(labeled_transcript, seg_start, seg_end)
            if not seg_transcript.strip():
                print(f"[S05] Segment {seg_idx+1}: empty transcript. Skipping.")
                continue

            seg_duration = seg_end - seg_start
            seg_max_candidates = max(3, int(max_candidates * (seg_duration / video_duration_s) * 1.5))

            seg_prompt = PROMPT
            seg_prompt = seg_prompt.replace("VIDEO_DURATION_PLACEHOLDER", str(int(seg_duration)))
            seg_prompt = seg_prompt.replace("MAX_CANDIDATES_PLACEHOLDER", str(seg_max_candidates))
            seg_prompt = seg_prompt.replace("CHANNEL_CONTEXT_PLACEHOLDER", channel_context)
            seg_prompt = seg_prompt.replace("GUEST_PROFILE_PLACEHOLDER", guest_profile_text)
            seg_prompt = seg_prompt.replace("LABELED_TRANSCRIPT_PLACEHOLDER", seg_transcript)
            seg_prompt = seg_prompt.replace("MIN_DURATION_PLACEHOLDER", str(min_duration))
            seg_prompt = seg_prompt.replace("MAX_DURATION_PLACEHOLDER", str(max_duration))

            try:
                raw_response = generate_json(seg_prompt, model=settings.GEMINI_MODEL_VIDEO)
            except Exception as model_err:
                print(f"[S05] Segment {seg_idx+1}: {settings.GEMINI_MODEL_VIDEO} failed ({model_err}). Falling back to {settings.GEMINI_MODEL_PRO}")
                try:
                    raw_response = generate_json(seg_prompt, model=settings.GEMINI_MODEL_PRO)
                except Exception as fallback_err:
                    print(f"[S05] Segment {seg_idx+1}: fallback model also failed: {fallback_err}. Skipping segment.")
                    continue

            if isinstance(raw_response, list):
                seg_candidates = raw_response
            elif isinstance(raw_response, dict) and "candidates" in raw_response:
                seg_candidates = raw_response["candidates"]
            elif isinstance(raw_response, str):
                seg_candidates = _parse_gemini_json(raw_response)
            else:
                seg_candidates = []

            print(f"[S05] Segment {seg_idx+1}: {len(seg_candidates)} raw candidates")
            all_raw_candidates.extend(seg_candidates)

        if not all_raw_candidates:
            print("[S05] Gemini returned no candidates from any segment. Returning empty list.")
            return []

        print(f"[S05] Total raw candidates across all segments: {len(all_raw_candidates)}")

        # 6. Validate, repair, and deduplicate
        valid_candidates = _validate_and_repair_candidates(all_raw_candidates, video_duration_s, min_duration, max_duration)
        print(f"[S05] {len(valid_candidates)} candidates after validation")

        # Deduplicate overlapping candidates from multi-segment discovery
        from app.pipeline.steps.s06_batch_evaluation import _deduplicate_by_overlap
        valid_candidates = _deduplicate_by_overlap(valid_candidates, overlap_threshold=0.5)
        print(f"[S05] {len(valid_candidates)} candidates after cross-segment dedup")

        # Reassign sequential candidate_id after merge + dedup
        for idx, c in enumerate(valid_candidates, start=1):
            c["candidate_id"] = idx

        return valid_candidates

    except Exception as e:
        print(f"[S05] Critical error: {e}")
        import traceback
        traceback.print_exc()
        return []
