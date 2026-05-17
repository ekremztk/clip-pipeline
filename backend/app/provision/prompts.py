from __future__ import annotations

import json
from typing import Any


EDIT_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "variant_mode": {"type": "string"},
        "score": {"type": "integer"},
        "recommended_start_s": {"type": "number"},
        "recommended_end_s": {"type": "number"},
        "internal_cuts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_s": {"type": "number"},
                    "end_s": {"type": "number"},
                    "reason": {"type": "string"},
                },
            },
        },
        "opening_assessment": {"type": "string"},
        "ending_assessment": {"type": "string"},
        "pacing_assessment": {"type": "string"},
        "standalone_assessment": {"type": "string"},
        "boundary_evidence": {
            "type": "object",
            "properties": {
                "opening_audio_evidence": {"type": "string"},
                "opening_word_timing_evidence": {"type": "string"},
                "ending_audio_evidence": {"type": "string"},
                "ending_word_timing_evidence": {"type": "string"},
            },
        },
        "keep_moments": {"type": "array", "items": {"type": "string"}},
        "remove_moments": {"type": "array", "items": {"type": "string"}},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "decision_summary": {"type": "string"},
        "editor_note": {"type": "string"},
    },
    "required": [
        "variant_mode",
        "score",
        "recommended_start_s",
        "recommended_end_s",
        "internal_cuts",
        "opening_assessment",
        "ending_assessment",
        "pacing_assessment",
        "standalone_assessment",
        "boundary_evidence",
        "keep_moments",
        "remove_moments",
        "risk_flags",
        "decision_summary",
        "editor_note",
    ],
}


def build_edit_plan_prompt(
    *,
    variant_mode: str,
    item: dict[str, Any],
    transcript_text: str,
    timed_words: list[dict[str, Any]],
    audio_analysis: dict[str, Any],
) -> str:
    timed_words_json = json.dumps(timed_words, ensure_ascii=False)
    audio_json = json.dumps(audio_analysis, ensure_ascii=False)

    return f"""
You are the Last Editor for Speedy Cast Clip, a YouTube Shorts channel built around English male celebrity talk-show and podcast clips.

Task:
Create an edit plan for the already-captioned MP4. The plan must improve the final Shorts version without changing the story or cutting the payoff.

Variant mode:
{variant_mode}

Mode behavior:
- conservative: only fix obvious bad start/end, half words, and long dead-air.
- tight: improve pacing while preserving setup, escalation, and punchline.
- aggressive: remove more hesitation and repeated filler, but never make the clip confusing.
- loop: favor a clean punchline ending and replayable final beat.

Hard rules:
- Do not remove context needed to understand who or what is being discussed.
- Do not cut laughter if it is the payoff or creates the loop effect.
- Do not rely on the transcript alone for half-word detection. ASR often omits clipped syllables or partial words, so a bad half-word start/end may not appear in the transcript.
- Inspect the actual first and last audible audio/video moment. Use timed_words as anchors, but verify whether the clip starts cleanly at the first real word or begins with an orphaned syllable, breath, clipped consonant, or missing setup word.
- If the opening is already clean, keep recommended_start_s at 0.0 or very close to 0.0 and explain why no opening trim is needed.
- If the ending is already clean, keep recommended_end_s near the original duration and explain why no ending trim is needed.
- For opening fixes, align to the nearest clean first-word start, not the middle of a word. The first retained word should feel naturally attached to the hook.
- For ending fixes, avoid ending in the middle of a word, phrase, or newly-started sentence. The final retained moment should feel intentional.
- Internal cuts are allowed only for distracting dead-air, repeated filler, irrelevant side remarks, or sections that weaken the story. Do not create cuts for tiny millisecond gaps that a viewer would not notice.
- Prefer word timestamps from the timed_words list for exact boundaries after deciding the edit from audio/video context.
- Explain exactly what changed and why. If you choose not to cut, explain why the original timing is already acceptable.

Clip metadata:
Title: {item.get("input_title") or ""}
Main person: {item.get("main_person") or ""}

Transcript:
{transcript_text[:7000]}

Timed words:
{timed_words_json[:12000]}

Audio analysis:
{audio_json[:7000]}

Return only one valid JSON object with this exact shape:
{{
  "variant_mode": "{variant_mode}",
  "score": 0,
  "recommended_start_s": 0.0,
  "recommended_end_s": 0.0,
  "internal_cuts": [
    {{"start_s": 0.0, "end_s": 0.0, "reason": ""}}
  ],
  "opening_assessment": "",
  "ending_assessment": "",
  "pacing_assessment": "",
  "standalone_assessment": "",
  "boundary_evidence": {{
    "opening_audio_evidence": "",
    "opening_word_timing_evidence": "",
    "ending_audio_evidence": "",
    "ending_word_timing_evidence": ""
  }},
  "keep_moments": [],
  "remove_moments": [],
  "risk_flags": [],
  "decision_summary": "",
  "editor_note": ""
}}
""".strip()
