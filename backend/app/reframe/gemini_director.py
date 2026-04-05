"""
Gemini Director — high-level creative direction for reframing.

Gemini's role is CREATIVE DIRECTION only:
  - Watch the video and understand what's happening
  - Identify subjects and their visual positions
  - Decide who the viewer should see at each moment and WHY
  - Diarization is provided as context, not as rules to follow

Gemini does NOT:
  - Provide pixel coordinates (MediaPipe does that)
  - Micromanage frame positions (path solver does that)
  - Just follow the active speaker (diarization already does that)
"""
import json
import logging
from typing import Optional

from .config import GeminiDirectorConfig
from .types import (
    DirectorPlan,
    FocusDirective,
    Frame,
    Shot,
    SubjectInfo,
)

logger = logging.getLogger(__name__)


def analyze_video(
    video_path: str,
    diarization_segments: list[dict],
    shots: list[Shot],
    frames: list[Frame],
    src_w: int,
    src_h: int,
    fps: float,
    duration_s: float,
    aspect_ratio: tuple[int, int],
    config: GeminiDirectorConfig,
) -> DirectorPlan:
    """
    Send full video to Gemini Pro for creative direction.

    Returns a DirectorPlan with subject info and focus directives.
    Raises on failure — caller should catch and use fallback.
    """
    from app.services.gemini_client import analyze_video as gemini_analyze_video
    from app.config import settings

    model = config.model or settings.GEMINI_MODEL_PRO

    prompt = _build_prompt(
        diarization_segments, shots, frames,
        src_w, src_h, duration_s, aspect_ratio,
        config.content_type_hint,
    )

    logger.info(
        "[GeminiDirector] Sending video (%s), hint=%s, %.1fs, %d shots, %d diar segments",
        model, config.content_type_hint, duration_s, len(shots), len(diarization_segments),
    )

    raw = gemini_analyze_video(video_path, prompt, model=model, json_mode=True)
    logger.info("[GeminiDirector] Response: %d chars", len(raw))

    plan = _parse_response(raw, duration_s)

    logger.info(
        "[GeminiDirector] Plan: type=%s, %d subjects, %d directives",
        plan.content_type, len(plan.subjects), len(plan.directives),
    )
    for s in plan.subjects:
        logger.info("[GeminiDirector]   Subject %s: position=%s, desc='%s'", s.id, s.position, s.description)
    for d in plan.directives:
        logger.info(
            "[GeminiDirector]   %.1f-%.1fs → subject=%s importance=%s reason='%s'",
            d.start_s, d.end_s, d.subject_id, d.importance, d.reason,
        )

    return plan


def build_fallback_plan(
    diarization_segments: list[dict],
    shots: list[Shot],
    duration_s: float,
) -> DirectorPlan:
    """Simple diarization-based fallback when Gemini fails."""
    logger.warning("[GeminiDirector] Using diarization fallback")

    subjects = [
        SubjectInfo(id="A", position="left", description="speaker 0"),
        SubjectInfo(id="B", position="right", description="speaker 1"),
    ]
    speaker_to_subject = {0: "A", 1: "B"}

    if not diarization_segments:
        return DirectorPlan(
            content_type="unknown", layout="unknown",
            subjects=[SubjectInfo(id="A", position="center", description="unknown")],
            directives=[FocusDirective(
                start_s=0.0, end_s=duration_s, subject_id="A",
                importance="medium", reason="no_data_fallback",
            )],
        )

    # Build directives from diarization
    directives: list[FocusDirective] = []
    for seg in diarization_segments:
        speaker = seg.get("speaker", 0)
        subj = speaker_to_subject.get(speaker, "A")
        directives.append(FocusDirective(
            start_s=seg.get("start", 0), end_s=seg.get("end", 0),
            subject_id=subj, importance="high",
            reason=f"diarization_speaker_{speaker}",
        ))

    # Fill gaps and ensure full coverage
    directives = _fill_and_merge(directives, duration_s)

    return DirectorPlan(
        content_type="unknown", layout="side_by_side",
        subjects=subjects, directives=directives,
    )


# --- Prompt ------------------------------------------------------------------

def _build_prompt(
    diarization_segments: list[dict],
    shots: list[Shot],
    frames: list[Frame],
    src_w: int,
    src_h: int,
    duration_s: float,
    aspect_ratio: tuple[int, int],
    content_type_hint: str,
) -> str:
    ar_str = f"{aspect_ratio[0]}:{aspect_ratio[1]}"
    diar_text = _format_diarization(diarization_segments)
    scene_text = _format_scene_structure(shots)
    face_summary = _format_face_summary(shots, frames)

    hint = ""
    if content_type_hint and content_type_hint != "auto":
        hint = f"\nContent hint from user: '{content_type_hint}'. Use as a hint only."

    return f"""You are a world-class video editor reframing {src_w}x{src_h} horizontal video to {ar_str} vertical.

YOUR ROLE: Creative director. Decide what the viewer should see at every moment to create the most engaging vertical video. You make EDITORIAL decisions — not mechanical ones.

KEY PRINCIPLE: Diarization tells you who's talking. Your value is understanding VISUAL STORYTELLING: reactions, body language, comedic timing, emotional beats, physical interactions, tension, surprise.
{hint}
CONTEXT DATA:

Scene structure:
{scene_text}

Face detection summary:
{face_summary}

Audio timeline (reference — not rules):
{diar_text}

Duration: {duration_s:.1f}s
Source: {src_w}x{src_h} → Target: {ar_str}

YOUR TASK:
1. Identify all visible subjects (give each an ID: A, B, C...) and their typical position in wide shots
2. Create a focus plan: who to show and why, moment by moment

DECISION GUIDELINES:
- Showing a REACTION can be more powerful than showing the speaker
- During cross-talk: pick whoever has stronger visual presence — do NOT bounce between them
- Physical comedy, gestures, dramatic body language → capture it even if that person isn't talking
- Close-up shots: just identify who's in them (framing is automatic)
- Camera angle changes: start a new segment at every scene cut
- Minimum segment: 1.5 seconds

OUTPUT — Return ONLY valid JSON:

{{
  "content_type": "<podcast|interview|talk_show|presentation|vlog|tutorial|sports|gaming|music|other>",
  "layout": "<side_by_side|single_person|over_shoulder|panel|stage|other>",
  "subjects": [
    {{"id": "A", "position": "left", "description": "brief visual description"}},
    {{"id": "B", "position": "right", "description": "brief visual description"}}
  ],
  "focus_plan": [
    {{
      "start_s": 0.0,
      "end_s": 4.2,
      "subject_id": "A",
      "importance": "high",
      "reason": "brief creative reason"
    }}
  ]
}}

SUBJECT ID RULES (CRITICAL — violating these causes hard visual bugs):
- The target output is a VERTICAL frame. Every unique human or active entity visible on screen MUST receive its own Subject ID.
- Multiple entities must NEVER be grouped under a single Subject ID regardless of their spatial proximity or how close together they appear.
- If two people are both visible in a wide shot, they are two subjects (e.g. "A" and "B") — never one.
- A subject_id represents exactly one physical person or entity. Do not reuse an ID for a different person.

STRUCTURAL RULES:
1. First segment starts at 0.0, last ends at {duration_s:.1f}
2. Segments are contiguous (no gaps, no overlaps)
3. Each segment >= 1.5 seconds
4. Segment boundaries align with scene cuts
5. subject_id must match a subject from the subjects array
6. importance: "high" (must show this person), "medium" (preferred), "low" (filler)

Return JSON now."""


def _format_scene_structure(shots: list[Shot]) -> str:
    if not shots:
        return "Single continuous shot"
    if len(shots) == 1:
        s = shots[0]
        return f"[{s.start_s:.1f}s-{s.end_s:.1f}s] {s.shot_type}"

    lines = []
    descs = {"wide": "WIDE (2+ people)", "closeup": "CLOSE-UP (1 person)", "b_roll": "B-ROLL"}
    for i, s in enumerate(shots):
        line = f"Scene {i+1}: [{s.start_s:.1f}s-{s.end_s:.1f}s] {descs.get(s.shot_type, s.shot_type)}"
        if i > 0:
            line += " <- CAMERA CUT"
        lines.append(line)
    return "\n".join(lines)


def _format_face_summary(shots: list[Shot], frames: list[Frame]) -> str:
    """Summarize face detections per shot for Gemini context."""
    lines = []
    for shot_idx, shot in enumerate(shots):
        shot_frames = [f for f in frames if f.shot_index == shot_idx]
        if not shot_frames:
            lines.append(f"Scene {shot_idx+1}: no face data")
            continue

        face_counts = [len(f.faces) for f in shot_frames]
        avg_faces = sum(face_counts) / len(face_counts) if face_counts else 0

        # Get typical face positions
        all_faces_x = []
        for f in shot_frames:
            for face in f.faces:
                all_faces_x.append(face.face_x)

        if all_faces_x:
            positions = ", ".join(f"x={x:.2f}" for x in sorted(set(
                round(x, 1) for x in all_faces_x
            )))
            lines.append(f"Scene {shot_idx+1}: ~{avg_faces:.0f} faces, positions: {positions}")
        else:
            lines.append(f"Scene {shot_idx+1}: no faces detected")

    return "\n".join(lines)


def _format_diarization(segments: list[dict]) -> str:
    if not segments:
        return "No speech data. Decide from visual analysis only."
    lines = []
    for seg in segments:
        lines.append(f"[{seg.get('start',0):.1f}s-{seg.get('end',0):.1f}s] Speaker {seg.get('speaker',0)}")
    return "\n".join(lines)


# --- Parse + Validate --------------------------------------------------------

def _parse_response(raw: str, duration_s: float) -> DirectorPlan:
    text = raw.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()

    start = text.index("{")
    end = text.rindex("}")
    data = json.loads(text[start:end + 1])

    content_type = data.get("content_type", "unknown")
    layout = data.get("layout", "unknown")

    subjects = []
    for s in data.get("subjects", []):
        subjects.append(SubjectInfo(
            id=str(s.get("id", "A")),
            position=str(s.get("position", "center")),
            description=str(s.get("description", "")),
        ))

    valid_ids = {s.id for s in subjects}

    raw_directives = data.get("focus_plan", [])
    if not raw_directives:
        raise ValueError("Gemini returned empty focus_plan")

    directives = _validate_directives(raw_directives, duration_s, valid_ids)

    return DirectorPlan(
        content_type=content_type, layout=layout,
        subjects=subjects, directives=directives,
    )


def _validate_directives(
    raw: list[dict],
    duration_s: float,
    valid_ids: set[str],
) -> list[FocusDirective]:
    MIN_DURATION = 1.0

    directives: list[FocusDirective] = []
    for r in raw:
        subj = str(r.get("subject_id", "A"))
        if subj not in valid_ids and valid_ids:
            subj = next(iter(valid_ids))

        imp = str(r.get("importance", "medium"))
        if imp not in ("high", "medium", "low"):
            imp = "medium"

        directives.append(FocusDirective(
            start_s=float(r.get("start_s", 0)),
            end_s=float(r.get("end_s", 0)),
            subject_id=subj,
            importance=imp,
            reason=str(r.get("reason", ""))[:100],
        ))

    if not directives:
        raise ValueError("No valid directives")

    # Fix start at 0
    if directives[0].start_s != 0.0:
        directives[0] = FocusDirective(
            start_s=0.0, end_s=directives[0].end_s,
            subject_id=directives[0].subject_id,
            importance=directives[0].importance,
            reason=directives[0].reason,
        )

    # Fix contiguity
    for i in range(1, len(directives)):
        prev_end = directives[i - 1].end_s
        if abs(directives[i].start_s - prev_end) > 0.01:
            directives[i] = FocusDirective(
                start_s=prev_end, end_s=directives[i].end_s,
                subject_id=directives[i].subject_id,
                importance=directives[i].importance,
                reason=directives[i].reason,
            )

    # Fix end at duration
    if abs(directives[-1].end_s - duration_s) > 0.1:
        directives[-1] = FocusDirective(
            start_s=directives[-1].start_s, end_s=duration_s,
            subject_id=directives[-1].subject_id,
            importance=directives[-1].importance,
            reason=directives[-1].reason,
        )

    # Merge short segments
    merged: list[FocusDirective] = [directives[0]]
    for d in directives[1:]:
        if d.end_s - d.start_s < MIN_DURATION:
            prev = merged[-1]
            merged[-1] = FocusDirective(
                start_s=prev.start_s, end_s=d.end_s,
                subject_id=prev.subject_id,
                importance=prev.importance, reason=prev.reason,
            )
        else:
            merged.append(d)

    return merged


def _fill_and_merge(
    directives: list[FocusDirective],
    duration_s: float,
) -> list[FocusDirective]:
    """Fill gaps and merge consecutive same-subject directives (for fallback)."""
    if not directives:
        return [FocusDirective(
            start_s=0.0, end_s=duration_s, subject_id="A",
            importance="medium", reason="empty_fallback",
        )]

    # Sort by start
    directives.sort(key=lambda d: d.start_s)

    filled: list[FocusDirective] = []

    # Fill gap before first
    if directives[0].start_s > 0.1:
        filled.append(FocusDirective(
            start_s=0.0, end_s=directives[0].start_s,
            subject_id=directives[0].subject_id,
            importance="low", reason="pre_fill",
        ))

    for d in directives:
        if filled and d.start_s > filled[-1].end_s + 0.05:
            filled[-1] = FocusDirective(
                start_s=filled[-1].start_s, end_s=d.start_s,
                subject_id=filled[-1].subject_id,
                importance=filled[-1].importance, reason=filled[-1].reason,
            )
        filled.append(d)

    # Extend last to duration
    if filled[-1].end_s < duration_s - 0.1:
        filled[-1] = FocusDirective(
            start_s=filled[-1].start_s, end_s=duration_s,
            subject_id=filled[-1].subject_id,
            importance=filled[-1].importance, reason=filled[-1].reason,
        )

    # Fix start
    if filled[0].start_s != 0.0:
        filled[0] = FocusDirective(
            start_s=0.0, end_s=filled[0].end_s,
            subject_id=filled[0].subject_id,
            importance=filled[0].importance, reason=filled[0].reason,
        )

    # Merge consecutive same subject
    merged: list[FocusDirective] = [filled[0]]
    for d in filled[1:]:
        if d.subject_id == merged[-1].subject_id:
            merged[-1] = FocusDirective(
                start_s=merged[-1].start_s, end_s=d.end_s,
                subject_id=merged[-1].subject_id,
                importance=merged[-1].importance, reason=merged[-1].reason,
            )
        else:
            merged.append(d)

    return merged
