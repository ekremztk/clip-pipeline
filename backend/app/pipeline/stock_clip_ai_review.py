from __future__ import annotations

import json
import os
import re
import tempfile
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import psycopg2
from psycopg2.extras import Json, RealDictCursor

from app.config import settings
from app.services.gemini_client import (
    analyze_video,
    get_accumulated_token_usage,
    reset_token_accumulator,
)
from app.services.supabase_client import get_db_url


REVIEWER = "gemini"

REVIEW_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "gemini_score": {"type": "integer"},
        "viral_score": {"type": "integer"},
        "channel_fit_score": {"type": "integer"},
        "publish_priority_score": {"type": "integer"},
        "hook_score": {"type": "integer"},
        "retention_score": {"type": "integer"},
        "visual_reaction_score": {"type": "integer"},
        "audio_energy_score": {"type": "integer"},
        "titleability_score": {"type": "integer"},
        "thumbnail_score": {"type": "integer"},
        "loop_score": {"type": "integer"},
        "risk_score": {"type": "integer"},
        "opening": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "has_half_word": {"type": "boolean"},
                "starts_too_early": {"type": "boolean"},
                "starts_too_late": {"type": "boolean"},
                "assessment": {"type": "string"},
            },
        },
        "ending": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "has_half_word": {"type": "boolean"},
                "ends_too_early": {"type": "boolean"},
                "ends_too_late": {"type": "boolean"},
                "assessment": {"type": "string"},
            },
        },
        "boundaries": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "assessment": {"type": "string"},
            },
        },
        "standalone_integrity": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "needs_context": {"type": "boolean"},
                "has_unclear_reference": {"type": "boolean"},
                "assessment": {"type": "string"},
            },
        },
        "viewer_effect": {"type": "string"},
        "title_feedback": {"type": "string"},
        "recommended_title": {"type": "string"},
        "recommended_description": {"type": "string"},
        "why_good": {"type": "string"},
        "why_bad": {"type": "string"},
        "reason_tags": {"type": "array", "items": {"type": "string"}},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "final_verdict": {"type": "string"},
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_connect():
    db_url = get_db_url()
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)


def _json_start_positions(text: str) -> list[int]:
    positions = [idx for idx, char in enumerate(text) if char in "{["]
    return [idx for idx in positions if text[idx] == "{"] + [idx for idx in positions if text[idx] == "["]


def _parse_json_object(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, count=1)
    if cleaned.endswith("```"):
        cleaned = re.sub(r"\s*```$", "", cleaned, count=1)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned).strip()

    decoder = json.JSONDecoder()
    for start in _json_start_positions(cleaned):
        try:
            value, _ = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
    return {}


def _build_json_repair_prompt(raw_text: str) -> str:
    return f"""
Convert the following malformed model response into exactly one valid JSON object.
Do not add analysis. Do not wrap in markdown. Keep only fields that are present or inferable.
If a value is missing, use null, false, 0, empty string, or empty array as appropriate.

Required top-level keys:
gemini_score, viral_score, channel_fit_score, publish_priority_score, hook_score,
retention_score, visual_reaction_score, audio_energy_score, titleability_score,
thumbnail_score, loop_score, risk_score, opening, ending, boundaries,
standalone_integrity, viewer_effect, title_feedback, recommended_title,
recommended_description, why_good, why_bad, reason_tags, risk_flags, final_verdict.

Malformed response:
{raw_text[:8000]}
""".strip()


def _repair_json_response(raw_text: str, model: str) -> dict[str, Any]:
    try:
        from app.services.gemini_client import generate

        repaired = generate(
            _build_json_repair_prompt(raw_text),
            system="Return only one valid JSON object.",
            model=model,
            json_mode=True,
        )
        return _parse_json_object(repaired)
    except Exception as exc:
        print(f"[StockClipAIReview] JSON repair failed: {exc}")
        return {}


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _nested(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _build_review_prompt(clip: dict[str, Any]) -> str:
    transcript = (clip.get("transcript") or "").strip()
    if len(transcript) > 5000:
        transcript = transcript[:5000] + "\n[TRUNCATED]"

    return f"""
You are the second-stage quality judge for Speedy Cast Clip, a YouTube Shorts channel that publishes English male celebrity podcast and talk-show clips.

Evaluate this final S10 captioned MP4 using the actual video and audio first. Use the transcript only as support for exact wording and boundary checks.

Audience assumption:
- The viewer may recognize the main celebrity from films, TV, comedy, or interviews.
- The viewer has not watched the source episode.
- The clip must still make sense as a standalone short.

Channel preference:
- Funny stories, awkward moments, surprising admissions, strong celebrity dynamics, clear setup/payoff, and easy lowercase title format.
- Avoid low-energy filler, inside references, context-dependent fragments, weak openings, or clips that only look polished but do not create an emotional effect.

Main person: {clip.get("main_person") or ""}
Source title: {clip.get("source_title") or clip.get("video_title") or ""}
Existing title: {clip.get("suggested_title") or ""}
Existing description: {clip.get("suggested_description") or ""}
Claude/S06 score snapshot: {clip.get("claude_score") or ""}
Clip transcript:
{transcript}

Analyze in stages:
1. Opening boundary: Does the clip start cleanly? Is there a half word, missing setup, or late/early start?
2. Ending boundary: Does the clip end cleanly? Is there a half word, missing punchline, or early/late cut?
3. Standalone integrity: Can a viewer understand the clip without the full episode?
4. Reference clarity: If the clip uses he/she/they/this person/that guy, is the referent clear inside the clip?
5. Hook and retention: Is the first 1-2 seconds strong enough? Does pacing hold?
6. Emotional effect: Does it actually make the viewer laugh, smile, feel surprise, or want to replay?
7. Visual and audio support: Facial reactions, laughter, timing, camera cuts, audience response, body language.
8. Title/description fit: Does the title include the main person when useful, and does it represent the clip without overpromising?

Return only one valid JSON object with this exact shape:
{{
  "gemini_score": 0,
  "viral_score": 0,
  "channel_fit_score": 0,
  "publish_priority_score": 0,
  "hook_score": 0,
  "retention_score": 0,
  "visual_reaction_score": 0,
  "audio_energy_score": 0,
  "titleability_score": 0,
  "thumbnail_score": 0,
  "loop_score": 0,
  "risk_score": 0,
  "opening": {{
    "score": 0,
    "has_half_word": false,
    "starts_too_early": false,
    "starts_too_late": false,
    "assessment": ""
  }},
  "ending": {{
    "score": 0,
    "has_half_word": false,
    "ends_too_early": false,
    "ends_too_late": false,
    "assessment": ""
  }},
  "boundaries": {{
    "score": 0,
    "assessment": ""
  }},
  "standalone_integrity": {{
    "score": 0,
    "needs_context": false,
    "has_unclear_reference": false,
    "assessment": ""
  }},
  "viewer_effect": "",
  "title_feedback": "",
  "recommended_title": "",
  "recommended_description": "",
  "why_good": "",
  "why_bad": "",
  "reason_tags": [],
  "risk_flags": [],
  "final_verdict": "publish_now | good_backup | review_manually | reject"
}}
""".strip()


def _download_video(url: str, clip_id: str) -> str:
    suffix = ".mp4"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix=f"gemini_review_{clip_id}_")
    path = handle.name
    handle.close()
    try:
        with httpx.stream("GET", url, timeout=600.0, follow_redirects=True) as response:
            response.raise_for_status()
            with open(path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        return path
    except Exception:
        if os.path.exists(path):
            os.remove(path)
        raise


def _claim_next_clip_review(
    channel_id: str,
    user_id: str,
    batch_id: Optional[str],
    model: str,
) -> Optional[dict[str, Any]]:
    batch_filter = "AND c.stock_batch_id = %s" if batch_id else ""
    params: list[Any] = [channel_id, user_id, REVIEWER]
    if batch_id:
        params.append(batch_id)

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    c.id,
                    c.job_id,
                    c.channel_id,
                    c.user_id,
                    c.stock_batch_id,
                    c.stock_queue_item_id,
                    c.stock_source_run_id,
                    c.stock_candidate_id,
                    c.main_person,
                    c.video_captioned_path,
                    c.transcript,
                    c.suggested_title,
                    c.suggested_description,
                    c.video_title,
                    c.quality_notes,
                    c.success_score,
                    c.confidence,
                    scc.s06_score AS claude_score,
                    scc.s06_quality_verdict,
                    scc.s06_quality_notes,
                    scc.s10_caption_status,
                    ssr.source_title
                FROM clips c
                LEFT JOIN stock_clip_ai_reviews r
                    ON r.clip_id = c.id AND r.reviewer = %s
                LEFT JOIN stock_clip_candidates scc
                    ON scc.id = c.stock_candidate_id
                LEFT JOIN stock_source_runs ssr
                    ON ssr.id = c.stock_source_run_id
                WHERE c.channel_id = %s
                  AND c.user_id = %s
                  {batch_filter}
                  AND c.stock_batch_id IS NOT NULL
                  AND c.video_captioned_path IS NOT NULL
                  AND scc.s10_caption_status = 'completed'
                  AND r.id IS NULL
                ORDER BY c.created_at ASC
                LIMIT 25
                """,
                [REVIEWER, channel_id, user_id] + ([batch_id] if batch_id else []),
            )
            candidates = cur.fetchall()

            for clip in candidates:
                cur.execute(
                    """
                    INSERT INTO stock_clip_ai_reviews (
                        clip_id, job_id, channel_id, user_id, stock_batch_id,
                        stock_queue_item_id, stock_source_run_id, stock_candidate_id,
                        main_person, reviewer, model, status, source_title,
                        clip_title, clip_description, video_url, transcript_chars,
                        claude_score, started_at, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, 'processing', %s,
                        %s, %s, %s, %s,
                        %s, now(), now()
                    )
                    ON CONFLICT (clip_id, reviewer) DO NOTHING
                    RETURNING id
                    """,
                    (
                        clip["id"],
                        clip["job_id"],
                        clip["channel_id"],
                        clip["user_id"],
                        clip["stock_batch_id"],
                        clip["stock_queue_item_id"],
                        clip["stock_source_run_id"],
                        clip["stock_candidate_id"],
                        clip["main_person"],
                        REVIEWER,
                        model,
                        clip.get("source_title") or clip.get("video_title"),
                        clip.get("suggested_title"),
                        clip.get("suggested_description"),
                        clip.get("video_captioned_path"),
                        len(clip.get("transcript") or ""),
                        _as_int(clip.get("claude_score") or clip.get("success_score") or clip.get("confidence")),
                    ),
                )
                review = cur.fetchone()
                if review:
                    conn.commit()
                    data = dict(clip)
                    data["review_id"] = review["id"]
                    data["claude_score"] = _as_int(
                        data.get("claude_score") or data.get("success_score") or data.get("confidence")
                    )
                    return data
            conn.commit()
    return None


def _review_to_payload(review: dict[str, Any], raw: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    opening = _nested(raw, "opening")
    ending = _nested(raw, "ending")
    boundaries = _nested(raw, "boundaries")
    integrity = _nested(raw, "standalone_integrity")

    return {
        "status": "completed",
        "model": review["model"],
        "gemini_score": _as_int(raw.get("gemini_score")),
        "viral_score": _as_int(raw.get("viral_score")),
        "channel_fit_score": _as_int(raw.get("channel_fit_score")),
        "publish_priority_score": _as_int(raw.get("publish_priority_score")),
        "hook_score": _as_int(raw.get("hook_score")),
        "retention_score": _as_int(raw.get("retention_score")),
        "opening_score": _as_int(opening.get("score")),
        "ending_score": _as_int(ending.get("score")),
        "boundary_score": _as_int(boundaries.get("score")),
        "clip_integrity_score": _as_int(integrity.get("score")),
        "context_clarity_score": _as_int(integrity.get("score")),
        "visual_reaction_score": _as_int(raw.get("visual_reaction_score")),
        "audio_energy_score": _as_int(raw.get("audio_energy_score")),
        "titleability_score": _as_int(raw.get("titleability_score")),
        "thumbnail_score": _as_int(raw.get("thumbnail_score")),
        "loop_score": _as_int(raw.get("loop_score")),
        "risk_score": _as_int(raw.get("risk_score")),
        "has_half_word_start": _as_bool(opening.get("has_half_word")),
        "has_half_word_end": _as_bool(ending.get("has_half_word")),
        "starts_too_early": _as_bool(opening.get("starts_too_early")),
        "starts_too_late": _as_bool(opening.get("starts_too_late")),
        "ends_too_early": _as_bool(ending.get("ends_too_early")),
        "ends_too_late": _as_bool(ending.get("ends_too_late")),
        "has_unclear_reference": _as_bool(integrity.get("has_unclear_reference")),
        "needs_context": _as_bool(integrity.get("needs_context")),
        "final_verdict": raw.get("final_verdict"),
        "opening_assessment": opening.get("assessment"),
        "ending_assessment": ending.get("assessment"),
        "story_integrity_assessment": integrity.get("assessment"),
        "viewer_effect": raw.get("viewer_effect"),
        "title_feedback": raw.get("title_feedback"),
        "recommended_title": raw.get("recommended_title"),
        "recommended_description": raw.get("recommended_description"),
        "why_good": raw.get("why_good"),
        "why_bad": raw.get("why_bad"),
        "reason_tags": _as_list(raw.get("reason_tags")),
        "risk_flags": _as_list(raw.get("risk_flags")),
        "raw_response": Json(raw),
        "token_usage": Json(usage),
        "cost_usd": usage.get("cost_usd"),
        "error_message": None,
        "completed_at": _now(),
        "updated_at": _now(),
    }


def _update_review(review_id: str, payload: dict[str, Any]) -> None:
    keys = list(payload.keys())
    assignments = ", ".join(f"{key} = %s" for key in keys)
    values = [payload[key] for key in keys]
    values.append(review_id)
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE stock_clip_ai_reviews SET {assignments} WHERE id = %s",
                values,
            )


def _run_one_review(clip: dict[str, Any], model: str) -> bool:
    review_id = str(clip["review_id"])
    video_path = ""
    try:
        video_url = clip.get("video_captioned_path")
        if not video_url:
            raise RuntimeError("Clip has no video_captioned_path")
        video_path = _download_video(video_url, str(clip["id"]))

        parsed = {}
        usage = {}
        raw_text = ""
        for attempt in range(2):
            prompt = _build_review_prompt(clip)
            if attempt:
                prompt += "\n\nPrevious response was invalid JSON. Return only one valid JSON object matching the requested schema."
            reset_token_accumulator()
            raw_text = analyze_video(
                video_path,
                prompt,
                model=model,
                json_mode=True,
                response_schema=REVIEW_RESPONSE_SCHEMA,
                temperature=0.2,
            )
            usage = get_accumulated_token_usage()
            parsed = _parse_json_object(raw_text)
            if parsed:
                break
            print(f"[StockClipAIReview] Invalid JSON for clip {clip.get('id')} attempt={attempt + 1}/2")

        if not parsed:
            parsed = _repair_json_response(raw_text, settings.GEMINI_MODEL_FLASH)
        if not parsed:
            raise RuntimeError(f"Gemini returned no valid JSON object. Raw snippet: {raw_text[:500]}")

        payload = _review_to_payload({**clip, "model": model}, parsed, usage)
        _update_review(review_id, payload)
        print(f"[StockClipAIReview] Clip {clip['id']} reviewed: score={payload.get('gemini_score')}")
        return True
    except Exception as exc:
        print(f"[StockClipAIReview] Clip {clip.get('id')} failed: {exc}")
        _update_review(review_id, {
            "status": "failed",
            "error_message": str(exc)[:2000],
            "completed_at": _now(),
            "updated_at": _now(),
        })
        return False
    finally:
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except Exception:
                pass


def run_stock_clip_ai_review_worker(
    channel_id: str,
    user_id: str,
    batch_id: Optional[str],
    limit: int,
    concurrency: int,
    model: Optional[str] = None,
) -> None:
    model = model or settings.GEMINI_MODEL_VIDEO
    max_workers = max(1, min(concurrency, limit))
    started = 0
    completed = 0
    failed = 0
    active = {}
    print(
        f"[StockClipAIReview] Starting channel={channel_id} batch={batch_id or '*'} "
        f"limit={limit} concurrency={max_workers} model={model}"
    )

    def submit_next(executor: ThreadPoolExecutor) -> bool:
        nonlocal started
        if started >= limit:
            return False
        clip = _claim_next_clip_review(channel_id, user_id, batch_id, model)
        if not clip:
            return False
        started += 1
        future = executor.submit(_run_one_review, clip, model)
        active[future] = str(clip["id"])
        print(f"[StockClipAIReview] Claimed clip={clip['id']} {started}/{limit}")
        return True

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while len(active) < max_workers and submit_next(executor):
            pass

        while active:
            done, _ = wait(active.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                active.pop(future)
                try:
                    ok = future.result()
                    if ok:
                        completed += 1
                    else:
                        failed += 1
                except Exception as exc:
                    print(f"[StockClipAIReview] Worker future failed unexpectedly: {exc}")
                    failed += 1

            while len(active) < max_workers and started < limit:
                if not submit_next(executor):
                    break

    print(f"[StockClipAIReview] Finished started={started} completed={completed} failed={failed}")
