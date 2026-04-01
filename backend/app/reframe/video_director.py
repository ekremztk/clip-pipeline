"""
Video Director — Gemini Pro full-video analysis for focus decisions.

Sends the entire video + diarization context to Gemini Pro in a single call.
Returns a DirectorPlan: who to focus on, when to switch, how to transition.

This replaces the old multi-module approach (gemini_director + focus_selector +
camera_path) with one unified AI decision layer.

Fallback: if Gemini fails, returns a simple diarization-based plan.
"""
import json
import logging
from typing import Optional

from .config import VideoDirectorConfig
from .types import DirectorPlan, FocusSegment, Shot, SpeakerInfo

logger = logging.getLogger(__name__)


# --- Style Guides (content-type agnostic, extensible) ------------------------
# Adding a new style = adding one entry here. Zero code changes needed.

STYLE_GUIDES: dict[str, str] = {
    "conversation": """STYLE: Conversation (podcast, interview, dialogue)

FOCUS RULES:
- Always focus on the ACTIVE SPEAKER. The person currently talking gets the frame.
- When a different person starts speaking, IMMEDIATELY cut to them. Use "cut" transition.
  Do NOT pan or slide between speakers — ALWAYS hard cut.
- You may briefly (2-3 seconds max) show the LISTENER only if they have a strong,
  clearly visible reaction: laughing, looking shocked, nodding enthusiastically, or
  making an expressive gesture. Then cut back to the speaker.
- During silence or cross-talk: stay on whoever spoke last.
- If one person is speaking for a long time (>15 seconds), you may cut to the listener
  for a brief reaction shot (2-3s) if they show visible engagement, then cut back.

FRAMING:
- Keep the subject's face in the upper third of the vertical frame.
- When a person gestures or leans, the crop should follow them naturally.
""",

    "presentation": """STYLE: Presentation (talk, demo, tutorial, monologue)

FOCUS RULES:
- Follow the PRESENTER as the primary subject at all times.
- Use "smooth" transition when the presenter moves across the frame.
- If the presenter gestures toward something off-screen, maintain focus on them
  unless another person enters the frame.
- For multi-person presentations: focus on whoever is actively presenting or
  demonstrating. Cut on speaker changes.

FRAMING:
- Keep the presenter centered with headroom above.
- Follow their movement with smooth tracking.
""",

    "action": """STYLE: Action (sports, gaming, vlog, dynamic content)

FOCUS RULES:
- Follow the PRIMARY ACTION — the most visually dynamic element.
- Use "smooth" transitions when tracking movement.
- Cut quickly between subjects during fast-paced sequences.
- Prioritize visual interest and motion over audio cues.

FRAMING:
- Center on the action with room for movement direction.
- Allow more dynamic reframing than conversation style.
""",

    "auto": """STYLE: Auto-detect

First, analyze the video to determine its content type (conversation, presentation,
action, or other). Then apply the most appropriate focus strategy.

General principles:
- Active speakers should be in frame when they talk.
- Speaker changes should trigger focus changes.
- Reactions are secondary — only show if visually compelling.
- Hard cut for subject changes, smooth only for same-subject movement.
- Keep faces in the upper third of the vertical frame.
""",
}


# --- Prompt Builder ----------------------------------------------------------

def _build_prompt(
    diarization_segments: list[dict],
    shots: list[Shot],
    src_w: int,
    src_h: int,
    duration_s: float,
    aspect_ratio: tuple[int, int],
    style_key: str,
) -> str:
    """Build the complete Gemini prompt from components."""

    style_guide = STYLE_GUIDES.get(style_key, STYLE_GUIDES["auto"])
    ar_str = f"{aspect_ratio[0]}:{aspect_ratio[1]}"

    # Format diarization as human-readable timeline
    diar_text = _format_diarization(diarization_segments)

    # Format scene structure with shot types
    scene_structure_text = _format_scene_structure(shots)

    prompt = f"""You are a professional video editor and director. Your specialty is reframing horizontal video into vertical format while maintaining compelling visual storytelling.

TASK:
Analyze this video and create a precise focus plan for reframing it from {src_w}x{src_h} (horizontal) to {ar_str} (vertical) format. Decide WHO the camera focuses on at every moment and WHEN to switch between subjects.

{style_guide}

AUDIO SPEAKER TIMELINE (precise timestamps from speech analysis):
{diar_text}
Note: Speaker numbers (Speaker 0, Speaker 1, etc.) are from audio analysis. You must map them to visual positions (left, right, center) based on what you OBSERVE in the video.

SCENE STRUCTURE (from video analysis — camera angle types with timestamps):
{scene_structure_text}

CRITICAL — Camera angle rules:
- "wide" shots show 2+ people. You MUST choose which person to focus on and crop to them.
- "closeup" shots show only 1 person. Just center on them — do NOT try to switch focus.
- "b_roll" shots have no clear subject. Center crop, hold still.
- At EVERY camera angle change (scene cut), use "cut" transition — the image already jumps.
- Your segment boundaries MUST align with camera angle changes. Never create a segment
  that spans across two different camera angles.

VIDEO INFO:
- Duration: {duration_s:.1f} seconds
- Source: {src_w}x{src_h}
- Target: {ar_str} vertical

OUTPUT — Return ONLY a valid JSON object. No markdown, no explanation, no text before or after the JSON.

Schema:
{{
  "scene_analysis": {{
    "content_type": "podcast | interview | presentation | monologue | action | other",
    "num_speakers": <integer>,
    "layout": "side_by_side | single_person | over_shoulder | other",
    "speakers": [
      {{"position": "left", "description": "brief visual description"}},
      {{"position": "right", "description": "brief visual description"}}
    ]
  }},
  "focus_segments": [
    {{
      "start_s": 0.0,
      "end_s": 5.2,
      "target": "left",
      "transition_in": "cut",
      "reason": "brief reason for this focus choice"
    }}
  ]
}}

MANDATORY STRUCTURAL RULES — violating ANY of these makes the output unusable:
1. The FIRST segment MUST start at exactly 0.0
2. The LAST segment MUST end at exactly {duration_s:.1f}
3. Segments MUST be perfectly contiguous: segment[i].end_s == segment[i+1].start_s
   NO GAPS and NO OVERLAPS between segments.
4. Every segment must be at least 1.5 seconds long. If a speaker talks for less than
   1.5 seconds, merge it with the adjacent segment.
5. "target" MUST be one of the positions listed in scene_analysis.speakers.
6. "transition_in" MUST be either "cut" (instant switch) or "smooth" (gradual 0.3s pan).
7. Use "cut" for ALL speaker changes and scene cuts. Only use "smooth" when the SAME
   person moves significantly within a single segment.
8. Every speaker change you hear in the audio MUST produce a corresponding segment
   boundary. Do NOT ignore speaker switches — the viewer needs to see who is talking.

COMMON MISTAKES TO AVOID:
- Starting the first segment at a time other than 0.0
- Leaving gaps between segments (e.g., segment 1 ends at 5.0 but segment 2 starts at 5.2)
- Making segments shorter than 1.5 seconds (merge short responses with adjacent segments)
- Using "smooth" transition when switching between different people (always use "cut")
- Ignoring speaker changes — if Speaker 1 responds to Speaker 0, you MUST cut to Speaker 1
- Having overlapping segments
- Returning the JSON wrapped in markdown code blocks

Return the JSON now."""

    return prompt


def _format_scene_structure(shots: list[Shot]) -> str:
    """Format shot list with types as readable scene structure."""
    if not shots:
        return "Single continuous shot (no scene cuts detected)"

    if len(shots) == 1:
        shot = shots[0]
        type_desc = {"wide": "wide (2+ people visible)", "closeup": "close-up (1 person)", "b_roll": "b-roll/other"}
        return f"[{shot.start_s:.1f}s - {shot.end_s:.1f}s] {type_desc.get(shot.shot_type, shot.shot_type)}"

    lines: list[str] = []
    type_descs = {
        "wide": "WIDE (2+ people visible)",
        "closeup": "CLOSE-UP (1 person only)",
        "b_roll": "B-ROLL / other",
    }
    for i, shot in enumerate(shots):
        desc = type_descs.get(shot.shot_type, shot.shot_type)
        lines.append(f"Scene {i + 1}: [{shot.start_s:.1f}s - {shot.end_s:.1f}s] {desc}")
        if i > 0:
            lines[-1] += "  ← CAMERA CUT here"

    return "\n".join(lines)


def _format_diarization(segments: list[dict]) -> str:
    """Format diarization segments as readable timeline."""
    if not segments:
        return "No speech data available. Decide focus based on visual cues only."

    lines: list[str] = []
    for seg in segments:
        speaker = seg.get("speaker", 0)
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        lines.append(f"[{start:.1f}s - {end:.1f}s] Speaker {speaker}")

    return "\n".join(lines)


# --- Gemini Call + Parsing ---------------------------------------------------

def analyze_video_focus(
    video_path: str,
    diarization_segments: list[dict],
    shots: list[Shot],
    src_w: int,
    src_h: int,
    fps: float,
    duration_s: float,
    aspect_ratio: tuple[int, int],
    config: VideoDirectorConfig,
) -> DirectorPlan:
    """
    Send full video to Gemini Pro and get a complete focus plan.

    Returns DirectorPlan on success, raises on unrecoverable failure.
    Caller should catch exceptions and use fallback.
    """
    from app.services.gemini_client import analyze_video as gemini_analyze_video
    from app.config import settings

    model = config.model or settings.GEMINI_MODEL_PRO
    style_key = config.content_type or "auto"

    prompt = _build_prompt(
        diarization_segments, shots, src_w, src_h,
        duration_s, aspect_ratio, style_key,
    )

    logger.info(
        "[VideoDirector] Sending video to Gemini Pro (%s), style=%s, duration=%.1fs",
        model, style_key, duration_s,
    )

    # Call Gemini with video — reuse existing infrastructure from S05
    raw_response = gemini_analyze_video(
        video_path, prompt, model=model, json_mode=True,
    )

    logger.debug("[VideoDirector] Raw Gemini response: %s", raw_response[:500])

    # Parse and validate
    plan = _parse_director_response(raw_response, duration_s)

    logger.info(
        "[VideoDirector] Plan: type=%s, %d speakers, %d segments",
        plan.content_type, len(plan.speakers), len(plan.segments),
    )
    return plan


def _parse_director_response(raw: str, duration_s: float) -> DirectorPlan:
    """Parse Gemini JSON response into DirectorPlan with validation and repair."""
    # Strip markdown fences if present
    text = raw.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()

    # Find JSON object boundaries
    try:
        start = text.index("{")
        end = text.rindex("}")
        json_str = text[start:end + 1]
    except ValueError:
        raise ValueError(f"No JSON object found in Gemini response: {text[:200]}")

    data = json.loads(json_str)

    # Extract scene analysis
    scene = data.get("scene_analysis", {})
    content_type = scene.get("content_type", "unknown")
    layout = scene.get("layout", "unknown")

    speakers: list[SpeakerInfo] = []
    for sp in scene.get("speakers", []):
        speakers.append(SpeakerInfo(
            position=str(sp.get("position", "center")),
            description=str(sp.get("description", "")),
        ))

    # Extract and validate focus segments
    raw_segments = data.get("focus_segments", [])
    if not raw_segments:
        raise ValueError("Gemini returned empty focus_segments")

    segments = _validate_and_repair_segments(raw_segments, duration_s, speakers)

    return DirectorPlan(
        content_type=content_type,
        layout=layout,
        speakers=speakers,
        segments=segments,
    )


def _validate_and_repair_segments(
    raw_segments: list[dict],
    duration_s: float,
    speakers: list[SpeakerInfo],
) -> list[FocusSegment]:
    """
    Validate Gemini segments and repair common issues.

    Repairs:
    - First segment not starting at 0 → fix start
    - Last segment not ending at duration → extend end
    - Gaps between segments → extend previous segment
    - Overlaps → snap next segment start to previous end
    - Segments too short → merge with previous
    - Invalid targets → map to nearest valid position
    """
    valid_positions = {sp.position for sp in speakers}
    if not valid_positions:
        valid_positions = {"left", "right", "center"}

    MIN_DURATION = 1.0  # Repair threshold (slightly less than prompt's 1.5 for tolerance)

    segments: list[FocusSegment] = []

    for i, raw in enumerate(raw_segments):
        start = float(raw.get("start_s", 0))
        end = float(raw.get("end_s", 0))
        target = str(raw.get("target", "center"))
        transition = str(raw.get("transition_in", "cut"))
        reason = str(raw.get("reason", ""))[:100]

        # Validate target position
        if target not in valid_positions:
            # Try to find closest match
            if "left" in target.lower() and "left" in valid_positions:
                target = "left"
            elif "right" in target.lower() and "right" in valid_positions:
                target = "right"
            else:
                target = next(iter(valid_positions))
            logger.warning("[VideoDirector] Invalid target, repaired to '%s'", target)

        # Validate transition
        if transition not in ("cut", "smooth"):
            transition = "cut"

        segments.append(FocusSegment(
            start_s=start, end_s=end, target=target,
            transition_in=transition, reason=reason,
        ))

    if not segments:
        raise ValueError("No valid segments after parsing")

    # Repair: first segment starts at 0
    if segments[0].start_s != 0.0:
        logger.warning("[VideoDirector] First segment starts at %.2f, fixing to 0.0", segments[0].start_s)
        segments[0] = FocusSegment(
            start_s=0.0, end_s=segments[0].end_s, target=segments[0].target,
            transition_in="cut", reason=segments[0].reason,
        )

    # Repair: contiguity (no gaps, no overlaps)
    for i in range(1, len(segments)):
        prev_end = segments[i - 1].end_s
        curr_start = segments[i].start_s

        if abs(curr_start - prev_end) > 0.01:
            # Gap or overlap — snap current start to previous end
            segments[i] = FocusSegment(
                start_s=prev_end, end_s=segments[i].end_s, target=segments[i].target,
                transition_in=segments[i].transition_in, reason=segments[i].reason,
            )

    # Repair: last segment ends at duration
    if abs(segments[-1].end_s - duration_s) > 0.1:
        logger.warning("[VideoDirector] Last segment ends at %.2f, fixing to %.2f", segments[-1].end_s, duration_s)
        segments[-1] = FocusSegment(
            start_s=segments[-1].start_s, end_s=duration_s, target=segments[-1].target,
            transition_in=segments[-1].transition_in, reason=segments[-1].reason,
        )

    # Repair: merge segments that are too short
    merged: list[FocusSegment] = [segments[0]]
    for seg in segments[1:]:
        duration = seg.end_s - seg.start_s
        if duration < MIN_DURATION:
            # Merge with previous: extend previous end
            prev = merged[-1]
            merged[-1] = FocusSegment(
                start_s=prev.start_s, end_s=seg.end_s, target=prev.target,
                transition_in=prev.transition_in, reason=prev.reason,
            )
            logger.debug("[VideoDirector] Merged short segment (%.2fs) at %.1f", duration, seg.start_s)
        else:
            merged.append(seg)

    # First segment always has "cut" transition
    if merged[0].transition_in != "cut":
        merged[0] = FocusSegment(
            start_s=merged[0].start_s, end_s=merged[0].end_s, target=merged[0].target,
            transition_in="cut", reason=merged[0].reason,
        )

    # CRITICAL: force "cut" when target changes between segments
    # "smooth" is ONLY valid when same person continues (same target)
    for i in range(1, len(merged)):
        if merged[i].target != merged[i - 1].target and merged[i].transition_in != "cut":
            logger.debug(
                "[VideoDirector] Forcing cut at %.1fs: target changed %s → %s",
                merged[i].start_s, merged[i - 1].target, merged[i].target,
            )
            merged[i] = FocusSegment(
                start_s=merged[i].start_s, end_s=merged[i].end_s, target=merged[i].target,
                transition_in="cut", reason=merged[i].reason,
            )

    logger.info(
        "[VideoDirector] %d raw segments → %d validated segments",
        len(raw_segments), len(merged),
    )
    return merged


# --- Diarization Fallback ----------------------------------------------------

def build_fallback_plan(
    diarization_segments: list[dict],
    shots: list[Shot],
    duration_s: float,
) -> DirectorPlan:
    """
    Simple diarization-based fallback when Gemini fails.
    Maps speaker 0 → left, speaker 1 → right. Hard cut on speaker change.
    """
    logger.warning("[VideoDirector] Using diarization fallback plan")

    speakers = [
        SpeakerInfo(position="left", description="speaker 0"),
        SpeakerInfo(position="right", description="speaker 1"),
    ]

    speaker_to_position = {0: "left", 1: "right"}

    if not diarization_segments:
        # No diarization — single center segment
        return DirectorPlan(
            content_type="unknown",
            layout="unknown",
            speakers=[SpeakerInfo(position="center", description="unknown")],
            segments=[FocusSegment(
                start_s=0.0, end_s=duration_s, target="center",
                transition_in="cut", reason="no_data_fallback",
            )],
        )

    # Build segments from diarization
    raw_segments: list[FocusSegment] = []
    for seg in diarization_segments:
        speaker = seg.get("speaker", 0)
        target = speaker_to_position.get(speaker, "center")
        raw_segments.append(FocusSegment(
            start_s=seg.get("start", 0),
            end_s=seg.get("end", 0),
            target=target,
            transition_in="cut",
            reason=f"diarization_speaker_{speaker}",
        ))

    if not raw_segments:
        return DirectorPlan(
            content_type="unknown", layout="unknown", speakers=speakers,
            segments=[FocusSegment(
                start_s=0.0, end_s=duration_s, target="center",
                transition_in="cut", reason="empty_fallback",
            )],
        )

    # Fill gaps: ensure coverage from 0.0 to duration_s
    filled: list[FocusSegment] = []

    # Gap before first segment
    if raw_segments[0].start_s > 0.1:
        filled.append(FocusSegment(
            start_s=0.0, end_s=raw_segments[0].start_s,
            target=raw_segments[0].target, transition_in="cut",
            reason="pre_speech_fill",
        ))

    for i, seg in enumerate(raw_segments):
        # Gap between segments
        if filled and seg.start_s > filled[-1].end_s + 0.05:
            filled[-1] = FocusSegment(
                start_s=filled[-1].start_s, end_s=seg.start_s,
                target=filled[-1].target, transition_in=filled[-1].transition_in,
                reason=filled[-1].reason,
            )
        filled.append(seg)

    # Extend last segment to duration
    if filled[-1].end_s < duration_s - 0.1:
        filled[-1] = FocusSegment(
            start_s=filled[-1].start_s, end_s=duration_s,
            target=filled[-1].target, transition_in=filled[-1].transition_in,
            reason=filled[-1].reason,
        )

    # Fix start at 0
    if filled[0].start_s != 0.0:
        filled[0] = FocusSegment(
            start_s=0.0, end_s=filled[0].end_s, target=filled[0].target,
            transition_in="cut", reason=filled[0].reason,
        )

    # Merge consecutive segments with same target
    merged: list[FocusSegment] = [filled[0]]
    for seg in filled[1:]:
        if seg.target == merged[-1].target:
            merged[-1] = FocusSegment(
                start_s=merged[-1].start_s, end_s=seg.end_s,
                target=merged[-1].target, transition_in=merged[-1].transition_in,
                reason=merged[-1].reason,
            )
        else:
            merged.append(seg)

    return DirectorPlan(
        content_type="unknown",
        layout="side_by_side",
        speakers=speakers,
        segments=merged,
    )
