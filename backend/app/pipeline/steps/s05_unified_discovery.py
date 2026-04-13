import json
import re
from typing import Optional
from app.config import settings
from app.services.gemini_client import generate_json
from app.services.supabase_client import get_client
from app.pipeline.prompts.unified_discovery import PROMPT
from datetime import datetime, timezone, timedelta
from app.director.events import director_events


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


def _validate_candidates(candidates: list, video_duration_s: float, min_duration: int) -> list:
    """Filters out candidates with invalid timestamps before sending to S06."""
    valid = []
    for c in candidates:
        if not isinstance(c, dict) or "candidate_id" not in c:
            continue
        start = float(c.get("recommended_start", 0) or 0)
        end = float(c.get("recommended_end", 0) or 0)
        # Negative timestamp guard
        if start < 0:
            print(f"[S05] Dropped candidate {c.get('candidate_id')}: negative start {start:.1f}s")
            continue
        if end < 0:
            print(f"[S05] Dropped candidate {c.get('candidate_id')}: negative end {end:.1f}s")
            continue
        if video_duration_s > 0 and start >= video_duration_s:
            print(f"[S05] Dropped candidate {c.get('candidate_id')}: start {start:.1f}s >= video duration {video_duration_s:.1f}s")
            continue
        if end <= start:
            print(f"[S05] Dropped candidate {c.get('candidate_id')}: end {end:.1f}s <= start {start:.1f}s")
            continue
        if (end - start) < min_duration:
            print(f"[S05] Dropped candidate {c.get('candidate_id')}: duration {end - start:.1f}s < min {min_duration}s")
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

        print(f"[S05] Prompt built ({len(prompt)} chars). Sending transcript to Gemini...")

        # 5. Transcript-only discovery via generate_json (no video upload)
        raw_response = generate_json(prompt, model=settings.GEMINI_MODEL_PRO)

        # 6. Parse response — generate_json may return dict or list directly
        if isinstance(raw_response, list):
            candidates = raw_response
        elif isinstance(raw_response, dict) and "candidates" in raw_response:
            candidates = raw_response["candidates"]
        elif isinstance(raw_response, str):
            candidates = _parse_gemini_json(raw_response)
        else:
            candidates = []

        if candidates:
            print(f"[S05] Gemini returned {len(candidates)} candidates")
            valid_candidates = _validate_candidates(candidates, video_duration_s, min_duration)
            print(f"[S05] {len(valid_candidates)} valid candidates after validation")
            try:
                director_events.emit_sync(
                    module="module_1", event="s05_discovery_completed",
                    payload={"job_id": job_id, "candidate_count": len(valid_candidates)},
                    channel_id=channel_id,
                )
            except Exception:
                pass
            return valid_candidates

        print("[S05] Gemini returned no candidates. Returning empty list.")
        return []

    except Exception as e:
        print(f"[S05] Critical error: {e}")
        import traceback
        traceback.print_exc()
        return []
