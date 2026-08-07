"""
S06.5 — Publishing metadata.

Titles and descriptions used to be produced by the same call that decided
whether a clip was publishable at all. That call was carrying fifteen jobs, and
the two that mattered — is this understandable on its own, does it end where the
thought ends — competed for attention with writing ad copy.

So this runs separately, after the gate, over approved clips only. Nothing here
can accept or reject anything.
"""
import json
from typing import Optional

from app.pipeline.json_parser import parse_json_list_response
from app.services.claude_client import call_claude


SYSTEM_PROMPT = (
    "You write titles and descriptions for short-form video clips. "
    "Return ONLY a valid JSON array. No markdown, no preamble."
)


PROMPT = """Write a title and description for each clip below.

## SUBJECT
SUBJECT_BLOCK_PLACEHOLDER

## STYLE
TITLE_STYLE_PLACEHOLDER

DESCRIPTION_TEMPLATE_PLACEHOLDER

## RULES
- The title must describe what actually happens in the clip. Never promise something the clip does not deliver.
- State the situation; do not give away the payoff. "her daughter entered a school raffle behind her back" works because the outcome is still to come.
- Name the other people involved when the audience would recognise them — a second familiar name in the title is worth more than a vague description of one.
- Keep titles under 60 characters where the style allows it.
- Write in the same language as the transcript.

## CLIPS
CLIPS_PLACEHOLDER

## OUTPUT
Return ONLY a JSON array, one entry per clip, in the order given:

[
  {"candidate_id": 1, "suggested_title": "...", "suggested_description": "..."}
]
"""


def _subject_block(video_title: str, main_person: Optional[str]) -> str:
    person = (main_person or "").strip()
    if person:
        return (
            f"The clips are about {person}. Use this name, or a natural short form "
            f"of it, in every title and description.\nSource video: {video_title}"
        )
    return (
        "No subject name was supplied. Take the speaker's name from the transcript "
        f"if it is stated there; otherwise describe them without naming.\n"
        f"Source video: {video_title}"
    )


def _clip_block(clips: list) -> str:
    parts = []
    for c in clips:
        parts.append(json.dumps({
            "candidate_id": c.get("candidate_id"),
            "content_type": c.get("content_type"),
            "hook_text": c.get("hook_text"),
            "end_text": c.get("end_text"),
            "what_happens": c.get("reason"),
            "duration_s": round(
                float(c.get("recommended_end") or 0) - float(c.get("recommended_start") or 0), 1
            ),
        }, indent=2))
    return "\n\n---\n\n".join(parts)


def run(
    clips: list,
    channel_dna: dict,
    job_id: str,
    video_title: str = "",
    main_person: Optional[str] = None,
    allow_premium: bool = False,
    model_choice: Optional[str] = None,
) -> list:
    """
    Attach suggested_title / suggested_description to every clip.

    Returns the clips either way: metadata failing is a cosmetic problem, and
    dropping an approved clip over it would be worse than shipping it with a
    fallback title.
    """
    if not clips:
        return clips

    print(f"[S06.5] Generating metadata for {len(clips)} clip(s), job {job_id}")

    try:
        dna = channel_dna or {}
        title_style = (dna.get("title_style") or "").strip() or (
            "Lowercase, plain language, promises a story. No clickbait punctuation."
        )
        description_template = (dna.get("description_template") or "").strip()

        prompt = (
            PROMPT
            .replace("SUBJECT_BLOCK_PLACEHOLDER", _subject_block(video_title, main_person))
            .replace("TITLE_STYLE_PLACEHOLDER", f"Title style: {title_style}")
            .replace(
                "DESCRIPTION_TEMPLATE_PLACEHOLDER",
                f"Description template — follow it exactly:\n{description_template}"
                if description_template
                else "Description: one compact sentence describing what happens.",
            )
            .replace("CLIPS_PLACEHOLDER", _clip_block(clips))
        )

        raw = call_claude(
            content=[{"type": "text", "text": prompt}],
            system=SYSTEM_PROMPT,
            max_tokens=4000,
            allow_premium=allow_premium,
            model_choice=model_choice,
        )
        results = parse_json_list_response(raw, log_prefix="[S06.5]")
        by_id = {str(r.get("candidate_id")): r for r in results if isinstance(r, dict)}

        filled = 0
        for c in clips:
            r = by_id.get(str(c.get("candidate_id"))) or {}
            title = (r.get("suggested_title") or "").strip()
            desc = (r.get("suggested_description") or "").strip()
            if title:
                c["suggested_title"] = title
                filled += 1
            if desc:
                c["suggested_description"] = desc

        print(f"[S06.5] Metadata written for {filled}/{len(clips)} clip(s)")
        return clips

    except Exception as e:
        print(f"[S06.5] Metadata generation failed, clips keep their defaults: {e}")
        return clips
