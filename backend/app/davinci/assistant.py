from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from app.config import settings
from app.provision.json_utils import compact_words, parse_json_object
from app.provision.steps import p02_audio_analysis
from app.services.gemini_client import analyze_video, generate


ASSISTANT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "clip": {
            "type": "object",
            "properties": {
                "duration_s": {"type": "number"},
                "duration": {"type": "string"},
                "fps": {"type": "string"},
            },
        },
        "summary": {"type": "string"},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "title": {"type": "string"},
                    "needs_change": {"type": "boolean"},
                    "status": {"type": "string"},
                    "timecode": {"type": "string"},
                    "range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string"},
                            "end": {"type": "string"},
                            "start_s": {"type": "number"},
                            "end_s": {"type": "number"},
                        },
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string"},
                                "transcript_en": {"type": "string"},
                                "translation_tr": {"type": "string"},
                                "reason": {"type": "string"},
                                "confidence": {"type": "integer"},
                            },
                        },
                    },
                },
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["clip", "summary", "recommendations", "warnings"],
}


def _probe_video(video_path: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=avg_frame_rate,r_frame_rate,duration:format=duration",
            "-of",
            "json",
            video_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout or "{}")
    stream = ((data.get("streams") or [{}])[0]) or {}
    duration_s = float(stream.get("duration") or (data.get("format") or {}).get("duration") or 0)
    fps = _parse_fps(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1")
    return {
        "duration_s": round(duration_s, 3),
        "duration": _seconds_to_timecode(duration_s, fps),
        "fps": str(fps),
        "fps_value": fps,
    }


def _parse_fps(raw: str) -> float:
    try:
        if "/" in raw:
            num, den = raw.split("/", 1)
            denominator = float(den or 1)
            return round(float(num) / denominator, 3) if denominator else 0.0
        return round(float(raw), 3)
    except Exception:
        return 0.0


def _seconds_to_timecode(seconds: float, fps: float) -> str:
    seconds = max(0.0, float(seconds or 0.0))
    frame_rate = fps if fps > 0 else 30.0
    whole = int(seconds)
    frames = int(round((seconds - whole) * frame_rate))
    if frames >= int(round(frame_rate)):
        whole += 1
        frames = 0
    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"


def _build_prompt(
    *,
    metadata: dict[str, Any],
    transcript_text: str,
    words: list[dict[str, Any]],
    audio_analysis: dict[str, Any],
) -> str:
    timed_words_json = json.dumps(compact_words(words, limit=1200), ensure_ascii=False)
    audio_json = json.dumps(audio_analysis, ensure_ascii=False)
    clip_obj = {
        "duration_s": metadata["duration_s"],
        "duration": metadata["duration"],
        "fps": metadata["fps"],
    }
    return f"""
You are Prognot Assistant, a last-edit advisor for YouTube Shorts.

Your job is not to auto-edit the clip. Your job is to tell a human editor exactly how to make the clip cleaner for Shorts if changes are needed.

Goal:
- The final clip should have the strongest possible opening, middle pacing, and ending for YouTube Shorts.
- Improve retention, clarity, and loop value.
- Keep the story understandable for a viewer who has not watched the source episode.
- Preserve setup, escalation, punchline, laughter, or reaction if they create the emotional payoff.
- Do not force edits.
- Be concise. Every explanation must be direct and useful for an editor, not a long essay.

Boundary rules:
- ASR may omit partial syllables, so do not rely on transcript text alone for half-word detection.
- Use the actual video/audio first, then use Nova timed_words and FFmpeg silence_gaps as anchors.
- Do not invent timecodes. Every recommended start/end/cut boundary must be validated against Nova timed_words or FFmpeg silence_gaps.
- If the visual/audio judgment suggests a cut but there is no exact Nova word boundary, choose the closest clean word boundary or silence boundary and briefly explain that.
- If the opening is bad, recommend the exact clean start timecode and the first retained word or phrase.
- If the opening is already good, return Hook with needs_change=false and briefly explain why it works.
- For internal cuts, only recommend cuts for distracting silence, dead-air, repeated filler, irrelevant side remarks, confusing context, or pacing problems that weaken the clip.
- Do not create placeholder internal cuts.
- If the ending is bad, recommend the exact clean end timecode and the final retained word, phrase, laugh, or reaction.
- If the ending is already good, return End with needs_change=false and briefly explain why it lands cleanly.

Required output:
- Always return exactly one Hook recommendation.
- Return Cut 1, Cut 2, Cut 3 only when there is a real internal section to remove.
- Always return exactly one End recommendation.
- For every recommendation, include action, transcript_en, translation_tr, reason, and confidence.
- Keep every reason short and direct.

Clip metadata:
{json.dumps(clip_obj, ensure_ascii=False)}

Transcript:
{transcript_text[:9000]}

Timed words:
{timed_words_json[:18000]}

Audio analysis:
{audio_json[:9000]}

Return only one valid JSON object with this exact shape:
{{
  "clip": {json.dumps(clip_obj, ensure_ascii=False)},
  "summary": "",
  "recommendations": [
    {{
      "kind": "hook",
      "title": "Hook",
      "needs_change": false,
      "status": "keep",
      "timecode": "00:00:00:00",
      "range": {{"start": "", "end": "", "start_s": 0.0, "end_s": 0.0}},
      "items": [{{"action": "", "transcript_en": "", "translation_tr": "", "reason": "", "confidence": 0}}]
    }},
    {{
      "kind": "end",
      "title": "End",
      "needs_change": false,
      "status": "keep",
      "timecode": "{metadata["duration"]}",
      "range": {{"start": "", "end": "", "start_s": 0.0, "end_s": 0.0}},
      "items": [{{"action": "", "transcript_en": "", "translation_tr": "", "reason": "", "confidence": 0}}]
    }}
  ],
  "warnings": []
}}
""".strip()


def _repair_json(raw_text: str) -> dict[str, Any]:
    try:
        repaired = generate(
            f"""
Convert the malformed response below into exactly one valid JSON object.
Do not add markdown or commentary. Keep the shape: clip, summary, recommendations, warnings.

Malformed response:
{raw_text[:10000]}
""".strip(),
            system="Return only one valid JSON object.",
            model=settings.GEMINI_MODEL_FLASH,
            json_mode=True,
        )
        return parse_json_object(repaired)
    except Exception as exc:
        print(f"[DaVinciAssistant] JSON repair failed: {exc}")
        return {}


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return fallback


def _normalize_item(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"action": "", "transcript_en": item.strip(), "translation_tr": "", "reason": "", "confidence": 0}
    data = item if isinstance(item, dict) else {}
    return {
        "action": str(data.get("action") or "").strip(),
        "transcript_en": str(data.get("transcript_en") or data.get("text") or "").strip(),
        "translation_tr": str(data.get("translation_tr") or "").strip(),
        "reason": str(data.get("reason") or "").strip(),
        "confidence": max(0, min(100, _safe_int(data.get("confidence"), 0))),
    }


def _normalize_result(parsed: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    clip = parsed.get("clip") if isinstance(parsed.get("clip"), dict) else {}
    normalized_clip = {
        "duration_s": round(_safe_float(clip.get("duration_s"), metadata["duration_s"]), 3),
        "duration": str(clip.get("duration") or metadata["duration"]),
        "fps": str(clip.get("fps") or metadata["fps"]),
    }
    raw_recommendations = parsed.get("recommendations") if isinstance(parsed.get("recommendations"), list) else []
    recommendations: list[dict[str, Any]] = []
    cut_index = 1
    fps = _safe_float(metadata.get("fps_value"), 30.0) or 30.0

    for raw in raw_recommendations:
        data = raw if isinstance(raw, dict) else {}
        kind = str(data.get("kind") or data.get("type") or "cut").lower().strip()
        if kind not in {"hook", "cut", "end"}:
            kind = "cut"
        title = "Hook" if kind == "hook" else "End" if kind == "end" else f"Cut {cut_index}"
        if kind == "cut":
            cut_index += 1
        range_data = data.get("range") if isinstance(data.get("range"), dict) else {}
        start_s = _safe_float(range_data.get("start_s"), 0.0)
        end_s = _safe_float(range_data.get("end_s"), 0.0)
        recommendations.append(
            {
                "kind": kind,
                "title": title,
                "needs_change": bool(data.get("needs_change", kind == "cut")),
                "status": str(data.get("status") or ("remove" if kind == "cut" else "keep")).strip(),
                "timecode": str(
                    data.get("timecode")
                    or (_seconds_to_timecode(start_s, fps) if kind == "hook" and start_s else normalized_clip["duration"] if kind == "end" else "")
                ).strip(),
                "range": {
                    "start": str(range_data.get("start") or (_seconds_to_timecode(start_s, fps) if start_s else "")).strip(),
                    "end": str(range_data.get("end") or (_seconds_to_timecode(end_s, fps) if end_s else "")).strip(),
                    "start_s": round(start_s, 3),
                    "end_s": round(end_s, 3),
                },
                "items": [_normalize_item(item) for item in (data.get("items") or [])] or [_normalize_item(data)],
            }
        )

    if not any(item["kind"] == "hook" for item in recommendations):
        recommendations.insert(
            0,
            {
                "kind": "hook",
                "title": "Hook",
                "needs_change": False,
                "status": "keep",
                "timecode": "00:00:00:00",
                "range": {"start": "", "end": "", "start_s": 0.0, "end_s": 0.0},
                "items": [{"action": "", "transcript_en": "", "translation_tr": "", "reason": "Opening needs manual review.", "confidence": 0}],
            },
        )
    if not any(item["kind"] == "end" for item in recommendations):
        recommendations.append(
            {
                "kind": "end",
                "title": "End",
                "needs_change": False,
                "status": "keep",
                "timecode": normalized_clip["duration"],
                "range": {"start": "", "end": "", "start_s": 0.0, "end_s": 0.0},
                "items": [{"action": "", "transcript_en": "", "translation_tr": "", "reason": "Ending needs manual review.", "confidence": 0}],
            }
        )

    warnings = parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else []
    return {
        "clip": normalized_clip,
        "summary": str(parsed.get("summary") or "").strip(),
        "recommendations": recommendations,
        "warnings": [str(item).strip() for item in warnings if str(item).strip()],
    }


def analyze_clip(video_path: str) -> dict[str, Any]:
    metadata = _probe_video(video_path)
    audio_payload = p02_audio_analysis.run(video_path, f"davinci_{os.path.basename(video_path)}")
    prompt = _build_prompt(
        metadata=metadata,
        transcript_text=audio_payload.get("transcript_text") or "",
        words=audio_payload.get("words") or [],
        audio_analysis=audio_payload.get("audio_analysis") or {},
    )
    raw_text = analyze_video(
        video_path,
        prompt,
        model=settings.GEMINI_MODEL_VIDEO,
        json_mode=True,
        response_schema=ASSISTANT_RESPONSE_SCHEMA,
        temperature=0.2,
    )
    parsed = parse_json_object(raw_text) or _repair_json(raw_text)
    if not parsed:
        raise RuntimeError(f"Gemini returned no valid assistant JSON. Raw snippet: {raw_text[:500]}")
    result = _normalize_result(parsed, metadata)
    result["transcript"] = {
        "text": audio_payload.get("transcript_text") or "",
        "word_count": len(audio_payload.get("words") or []),
    }
    result["audio_analysis"] = audio_payload.get("audio_analysis") or {}
    return result
