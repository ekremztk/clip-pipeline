"""
Gemini semantic decision layer for reframe focus selection.

Identifies key decision points (shot boundaries, speaker changes, long scenes)
and asks Gemini Flash Lite to choose which person to focus on based on
annotated video frames with numbered bounding boxes.

Falls back gracefully — if Gemini fails, returns empty decisions
and focus_selector uses diarization-only logic.
"""
import json
import logging
import re
import subprocess
from typing import Optional

from .config import GeminiDirectorConfig
from .types import (
    DecisionPoint,
    FrameAnalysis,
    GeminiDecision,
    PersonDetection,
    Shot,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a video reframing AI. You analyze podcast/interview frames to decide which person the camera should focus on when cropping from 16:9 to 9:16 vertical format.

Each frame has numbered boxes [1], [2], etc. drawn around detected persons.

For each decision point, choose ONE person number to focus on. Consider:
- Who is actively speaking (if indicated)
- Who is reacting interestingly (facial expressions, gestures)
- Visual composition and framing quality
- If someone is presenting/gesturing, they may be more visually interesting than the listener

CRITICAL OUTPUT RULES — FOLLOW EXACTLY:
1. Return ONLY a valid JSON array. Nothing else.
2. Do NOT wrap the JSON in markdown code blocks (no ```json or ```).
3. Do NOT add any explanation, commentary, or text before or after the JSON.
4. The response must start with [ and end with ].

Format:
[{"time_s": 1.5, "target_person_index": 0, "reason": "speaking and gesturing", "confidence": 0.9}]

- target_person_index is 0-based (person [1] = index 0, person [2] = index 1)
- Keep reasons brief (3-5 words)
- confidence: 0.0-1.0"""


def calculate_decision_points(
    frame_analyses: list[FrameAnalysis],
    diarization_segments: list[dict],
    shots: list[Shot],
    config: GeminiDirectorConfig,
) -> list[DecisionPoint]:
    """
    Identify moments where Gemini should evaluate framing.

    Triggers:
    - shot_boundary: first multi-person frame after each shot cut
    - speaker_change: when diarization shows speaker switch
    - long_scene_check: every N seconds in scenes without other triggers
    """
    if not frame_analyses:
        return []

    decision_points: list[DecisionPoint] = []
    seen_times: set[float] = set()

    # Helper: get active speaker at time
    def get_speaker(t: float) -> Optional[int]:
        for seg in diarization_segments:
            if seg.get("start", 0) <= t <= seg.get("end", 0):
                return seg.get("speaker")
        return None

    # 1. Shot boundaries — first multi-person frame per shot
    for shot_idx, shot in enumerate(shots):
        for fa in frame_analyses:
            if fa.shot_index == shot_idx and len(fa.persons) >= 2:
                if fa.time_s not in seen_times:
                    decision_points.append(DecisionPoint(
                        time_s=fa.time_s,
                        trigger="shot_boundary",
                        shot_index=shot_idx,
                        persons=fa.persons,
                        active_speaker=get_speaker(fa.time_s),
                    ))
                    seen_times.add(fa.time_s)
                break

    # 2. Speaker changes
    prev_speaker = None
    for seg in diarization_segments:
        speaker = seg.get("speaker")
        if prev_speaker is not None and speaker != prev_speaker:
            change_time = seg["start"]
            # Find closest multi-person frame
            best_fa = _find_nearest_frame(frame_analyses, change_time, min_persons=2)
            if best_fa and best_fa.time_s not in seen_times:
                decision_points.append(DecisionPoint(
                    time_s=best_fa.time_s,
                    trigger="speaker_change",
                    shot_index=best_fa.shot_index,
                    persons=best_fa.persons,
                    active_speaker=speaker,
                ))
                seen_times.add(best_fa.time_s)
        prev_speaker = speaker

    # 3. Long scene checks — every N seconds where no other decision exists
    for shot_idx, shot in enumerate(shots):
        check_t = shot.start_s + config.long_scene_check_interval_s
        while check_t < shot.end_s - 1.0:
            # Skip if we already have a decision near this time
            if not any(abs(t - check_t) < 1.5 for t in seen_times):
                best_fa = _find_nearest_frame(
                    frame_analyses, check_t, min_persons=2, shot_index=shot_idx,
                )
                if best_fa and best_fa.time_s not in seen_times:
                    decision_points.append(DecisionPoint(
                        time_s=best_fa.time_s,
                        trigger="long_scene_check",
                        shot_index=best_fa.shot_index,
                        persons=best_fa.persons,
                        active_speaker=get_speaker(best_fa.time_s),
                    ))
                    seen_times.add(best_fa.time_s)
            check_t += config.long_scene_check_interval_s

    decision_points.sort(key=lambda dp: dp.time_s)
    logger.info(
        "[GeminiDirector] %d decision points: %s",
        len(decision_points),
        {dp.trigger for dp in decision_points},
    )
    return decision_points


def build_annotated_frames(
    video_path: str,
    decision_points: list[DecisionPoint],
    config: GeminiDirectorConfig,
) -> list[tuple[DecisionPoint, Optional[bytes]]]:
    """
    Extract frames at decision point times and draw numbered bounding boxes.
    Returns list of (decision_point, jpeg_bytes) tuples.
    """
    results: list[tuple[DecisionPoint, Optional[bytes]]] = []

    for dp in decision_points:
        if len(dp.persons) < 2:
            results.append((dp, None))
            continue

        try:
            frame_bytes = _extract_frame(video_path, dp.time_s, config.annotation_resolution)
            if frame_bytes:
                annotated = _draw_boxes(frame_bytes, dp.persons, config.annotation_resolution)
                results.append((dp, annotated))
            else:
                results.append((dp, None))
        except Exception as e:
            logger.warning("[GeminiDirector] Frame extraction failed at t=%.2f: %s", dp.time_s, e)
            results.append((dp, None))

    return results


def query_gemini_batch(
    annotated_frames: list[tuple[DecisionPoint, Optional[bytes]]],
    transcript_context: str,
    config: GeminiDirectorConfig,
) -> list[GeminiDecision]:
    """
    Send annotated frames to Gemini Flash Lite in batches.
    Returns list of GeminiDecision for each decision point.
    """
    from app.services.gemini_client import get_gemini_client
    from app.config import settings

    client = get_gemini_client()
    model_name = config.model or settings.GEMINI_MODEL_FLASH

    # Filter to only frames with images and 2+ persons
    valid_frames = [(dp, img) for dp, img in annotated_frames if img is not None]
    if not valid_frames:
        return []

    decisions: list[GeminiDecision] = []

    # Process in batches
    for batch_start in range(0, len(valid_frames), config.max_batch_size):
        batch = valid_frames[batch_start:batch_start + config.max_batch_size]
        try:
            batch_decisions = _query_batch(client, model_name, batch, transcript_context, config)
            decisions.extend(batch_decisions)
        except Exception as e:
            logger.warning("[GeminiDirector] Gemini batch failed: %s", e)
            # Skip this batch — diarization fallback will handle these times

    logger.info("[GeminiDirector] %d Gemini decisions from %d frames", len(decisions), len(valid_frames))
    return decisions


# --- Internal helpers ---------------------------------------------------------

def _find_nearest_frame(
    frame_analyses: list[FrameAnalysis],
    target_time: float,
    min_persons: int = 1,
    shot_index: Optional[int] = None,
) -> Optional[FrameAnalysis]:
    """Find the nearest frame analysis to target_time with enough persons."""
    best: Optional[FrameAnalysis] = None
    best_dist = float("inf")

    for fa in frame_analyses:
        if len(fa.persons) < min_persons:
            continue
        if shot_index is not None and fa.shot_index != shot_index:
            continue
        dist = abs(fa.time_s - target_time)
        if dist < best_dist and dist < 1.0:  # Max 1s away
            best = fa
            best_dist = dist

    return best


def _extract_frame(
    video_path: str,
    time_s: float,
    resolution: tuple[int, int],
) -> Optional[bytes]:
    """Extract a single frame as JPEG bytes using FFmpeg."""
    w, h = resolution
    cmd = [
        "ffmpeg", "-ss", str(round(time_s, 3)),
        "-i", video_path,
        "-vframes", "1",
        "-vf", f"scale={w}:{h}",
        "-f", "image2",
        "-c:v", "mjpeg",
        "-q:v", "5",
        "pipe:1",
    ]
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
    )
    if result.returncode != 0:
        return None
    return result.stdout if result.stdout else None


def _draw_boxes(
    jpeg_bytes: bytes,
    persons: list[PersonDetection],
    resolution: tuple[int, int],
) -> bytes:
    """Draw numbered bounding boxes on a JPEG frame. Returns annotated JPEG."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io

        img = Image.open(io.BytesIO(jpeg_bytes))
        draw = ImageDraw.Draw(img)
        w, h = resolution

        colors = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00"]

        for i, person in enumerate(persons):
            color = colors[i % len(colors)]
            # Convert normalized coords to pixel coords
            cx = person.center_x * w
            cy = person.center_y * h
            bw = person.bbox_width * w
            bh = person.bbox_height * h

            x1 = max(0, cx - bw / 2)
            y1 = max(0, cy - bh / 2)
            x2 = min(w, cx + bw / 2)
            y2 = min(h, cy + bh / 2)

            # Draw box
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

            # Draw label
            label = f"[{i + 1}]"
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
            except Exception:
                font = ImageFont.load_default()

            bbox = draw.textbbox((x1, y1 - 20), label, font=font)
            draw.rectangle(bbox, fill=color)
            draw.text((x1, y1 - 20), label, fill="white", font=font)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()

    except ImportError:
        logger.warning("[GeminiDirector] Pillow not available, returning raw frame")
        return jpeg_bytes


def _extract_json_array(raw: str) -> Optional[list]:
    """
    Robustly extract a JSON array from a Gemini response.
    Uses simple string operations (index/rindex) — no regex that can truncate.
    """
    if not raw:
        return None

    # 1. Strip markdown fences with plain string ops — never regex on the JSON body
    text = raw.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()

    # 2. Find first [ and last ] — guaranteed to include the full array
    try:
        start = text.index("[")
        end = text.rindex("]")
        candidate = text[start:end + 1]
    except ValueError:
        # No array brackets — try single object fallback
        try:
            s = text.index("{")
            e = text.rindex("}")
            obj_text = text[s:e + 1]
            return [json.loads(obj_text)]
        except (ValueError, json.JSONDecodeError):
            logger.warning("[GeminiDirector] No JSON array found in response: %s", raw[:200])
            return None

    # 3. Parse
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        # Last resort: strip trailing commas, replace single quotes
        fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
        fixed = fixed.replace("'", '"')
        try:
            parsed = json.loads(fixed)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError as e:
            logger.warning("[GeminiDirector] JSON parse failed: %s | candidate: %s", e, candidate[:300])
            return None


def _query_batch(
    client,
    model_name: str,
    batch: list[tuple[DecisionPoint, bytes]],
    transcript_context: str,
    config: GeminiDirectorConfig,
) -> list[GeminiDecision]:
    """Send a single batch of annotated frames to Gemini."""
    from google.genai import types

    # Build multimodal content parts
    contents = []

    prompt_text = _SYSTEM_PROMPT + "\n\n"
    if transcript_context:
        prompt_text += f"Transcript context:\n{transcript_context[:1000]}\n\n"

    for i, (dp, img_bytes) in enumerate(batch):
        speaker_info = f" (speaker {dp.active_speaker} is talking)" if dp.active_speaker is not None else ""
        prompt_text += f"Decision point {i + 1}: t={dp.time_s:.2f}s, trigger={dp.trigger}, {len(dp.persons)} persons{speaker_info}\n"

        contents.append(types.Part.from_text(text=prompt_text))
        prompt_text = ""  # Reset after first text block

        # Add image as inline data
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

    prompt_text += f"\nReturn a JSON array of exactly {len(batch)} objects, one per decision point above. Start with [ and end with ]."
    contents.append(types.Part.from_text(text=prompt_text))

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )

        raw = response.text or ""
        logger.debug("[GeminiDirector] Raw response: %s", raw[:300])

        parsed = _extract_json_array(raw)
        if not parsed:
            return []

        decisions: list[GeminiDecision] = []
        for j, item in enumerate(parsed):
            if j >= len(batch):
                break
            dp = batch[j][0]
            target_idx = int(item.get("target_person_index", 0))
            target_idx = max(0, min(target_idx, len(dp.persons) - 1))

            decisions.append(GeminiDecision(
                time_s=dp.time_s,
                target_person_index=target_idx,
                reason=str(item.get("reason", "gemini"))[:50],
                confidence=float(item.get("confidence", 0.8)),
            ))

        return decisions

    except Exception as e:
        logger.warning("[GeminiDirector] Gemini API error: %s", e)
        return []
