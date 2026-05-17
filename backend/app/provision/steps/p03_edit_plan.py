from __future__ import annotations

from typing import Any

from app.config import settings
from app.provision.json_utils import compact_words, parse_json_object
from app.provision.prompts import EDIT_PLAN_SCHEMA, build_edit_plan_prompt
from app.services.gemini_client import analyze_video, generate


def _repair_plan(raw_text: str) -> dict[str, Any]:
    repair_prompt = f"""
Convert the malformed response below into exactly one valid JSON object.
Do not add markdown. Keep only fields that are present or inferable.
Use empty arrays, empty strings, 0, or false for missing values.

Malformed response:
{raw_text[:8000]}
""".strip()
    try:
        repaired = generate(
            repair_prompt,
            system="Return only one valid JSON object.",
            model=settings.GEMINI_MODEL_FLASH,
        )
        return parse_json_object(repaired)
    except Exception as exc:
        print(f"[Provision/P03] JSON repair failed: {exc}")
        return {}


def _sanitize_plan(plan: dict[str, Any], variant_mode: str, duration_s: float) -> dict[str, Any]:
    start_s = float(plan.get("recommended_start_s") or 0)
    end_s = float(plan.get("recommended_end_s") or duration_s or 0)
    if duration_s > 0:
        start_s = max(0.0, min(start_s, duration_s))
        end_s = max(start_s, min(end_s, duration_s))

    internal_cuts = []
    for cut in plan.get("internal_cuts") or []:
        if not isinstance(cut, dict):
            continue
        cut_start = float(cut.get("start_s") or 0)
        cut_end = float(cut.get("end_s") or 0)
        if cut_end <= cut_start:
            continue
        if duration_s > 0:
            cut_start = max(start_s, min(cut_start, end_s))
            cut_end = max(cut_start, min(cut_end, end_s))
        internal_cuts.append(
            {
                "start_s": round(cut_start, 3),
                "end_s": round(cut_end, 3),
                "reason": str(cut.get("reason") or ""),
            }
        )

    return {
        "variant_mode": str(plan.get("variant_mode") or variant_mode),
        "score": int(plan.get("score") or 0),
        "recommended_start_s": round(start_s, 3),
        "recommended_end_s": round(end_s, 3),
        "internal_cuts": internal_cuts,
        "opening_assessment": str(plan.get("opening_assessment") or ""),
        "ending_assessment": str(plan.get("ending_assessment") or ""),
        "pacing_assessment": str(plan.get("pacing_assessment") or ""),
        "standalone_assessment": str(plan.get("standalone_assessment") or ""),
        "boundary_evidence": plan.get("boundary_evidence") if isinstance(plan.get("boundary_evidence"), dict) else {},
        "keep_moments": [str(item) for item in (plan.get("keep_moments") or [])],
        "remove_moments": [str(item) for item in (plan.get("remove_moments") or [])],
        "risk_flags": [str(item) for item in (plan.get("risk_flags") or [])],
        "decision_summary": str(plan.get("decision_summary") or ""),
        "editor_note": str(plan.get("editor_note") or ""),
    }


def run(
    *,
    video_path: str,
    item: dict[str, Any],
    variant_mode: str,
    transcript_text: str,
    words: list[dict[str, Any]],
    audio_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Ask Gemini for one edit plan variant."""
    duration_s = float(audio_analysis.get("duration_s") or 0)
    prompt = build_edit_plan_prompt(
        variant_mode=variant_mode,
        item=item,
        transcript_text=transcript_text,
        timed_words=compact_words(words),
        audio_analysis=audio_analysis,
    )
    raw_text = analyze_video(
        video_path,
        prompt,
        model=settings.GEMINI_MODEL_VIDEO,
        json_mode=True,
        response_schema=EDIT_PLAN_SCHEMA,
        temperature=0.2,
    )
    plan = parse_json_object(raw_text)
    if not plan:
        plan = _repair_plan(raw_text)
    if not plan:
        raise RuntimeError(f"Gemini returned no valid edit plan. Raw snippet: {raw_text[:500]}")
    return _sanitize_plan(plan, variant_mode, duration_s)
