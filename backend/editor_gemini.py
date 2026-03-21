# EDITOR MODULE — Isolated module, no dependencies on other project files

import json
import logging
import os
import tempfile
from google import genai
from google.genai import types

logger = logging.getLogger("editor.gemini")

_editor_gemini_client = None

def get_editor_gemini_client() -> genai.Client:
    """Lazy initialization of Vertex AI client for editor module."""
    global _editor_gemini_client
    if _editor_gemini_client is None:
        gcp_credentials = os.getenv("GCP_CREDENTIALS_JSON", "")
        gcp_project = os.getenv("GCP_PROJECT", "")
        gcp_location = os.getenv("GCP_LOCATION", "us-central1")

        if gcp_credentials:
            fd, temp_path = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, 'w') as f:
                f.write(gcp_credentials)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_path

        _editor_gemini_client = genai.Client(
            vertexai=True,
            project=gcp_project,
            location=gcp_location
        )
        logger.info(f"[EditorGemini] Vertex AI client initialized for project {gcp_project}")
    return _editor_gemini_client

EDITOR_PROMPT_TEMPLATE = """
You are a professional YouTube Shorts video editor specializing in viral podcast clips.
Your task: analyze this transcript and make precise editing decisions for a 9:16 vertical video.
Target maximum duration: {target_max_duration} seconds.

RULES:
- Output ONLY valid JSON matching the exact schema below. No markdown, no explanations.
- Cuts: Only remove genuine silences (>0.3s), filler words (uh, um, like, you know), clear repetitions.
  NEVER cut mid-sentence. NEVER cut meaningful content.
- Hook: Pick the most emotionally charged, surprising, or opinionated statement.
- Commentary cards: Add EDITORIAL VALUE — context, emphasis, surprising facts. Max 4 cards.
- Speed sections: Only for genuinely slow/low-energy sections. Max multiplier 1.20.
- First think through your strategy in '_reasoning', THEN provide your decisions.
  This ensures your cuts and hook are well-considered before committing.

<transcript>
{transcript_text}
</transcript>

<silences>
{silence_summary}
</silences>

<metadata>
Duration: {duration}s | Speakers: {speaker_count}
</metadata>

Respond with this exact JSON schema:
{{
  "_reasoning": "string — your internal editorial strategy before deciding (2-3 sentences max)",
  "hook_start": float,
  "hook_reason": "string (max 100 chars)",
  "hook_score": int (0-100),
  "cuts": [
    {{
      "remove_from": float,
      "remove_to": float,
      "reason": "silence|filler_word|repetition|low_energy"
    }}
  ],
  "speed_sections": [
    {{
      "from": float,
      "to": float,
      "multiplier": float (1.05 to 1.20 only)
    }}
  ],
  "commentary_cards": [
    {{
      "text": "string (max 40 chars)",
      "at": float,
      "duration": float (2.0 to 4.0),
      "position": "top|center|bottom"
    }}
  ],
  "title_suggestion": "string (max 60 chars)",
  "description_suggestion": "string (2-3 sentences)",
  "total_duration_estimate": float
}}
"""

def build_transcript_text(transcript: list[dict]) -> str:
    """
    Converts word-level transcript to compact readable format.
    Example output:
    [0.0s SPEAKER_0] Hello everyone welcome to the show
    [4.2s SPEAKER_1] Thanks for having me I really appreciate it
    """
    lines = []
    current_speaker = None
    current_line_start = 0.0
    current_words = []

    for word in transcript:
        if word.get('speaker') != current_speaker:
            if current_words:
                lines.append(f"[{current_line_start:.1f}s SPEAKER_{current_speaker}] {' '.join(current_words)}")
            current_speaker = word.get('speaker')
            current_line_start = word.get('start', 0.0)
            current_words = []
        current_words.append(word.get('word', ''))

    if current_words:
        lines.append(f"[{current_line_start:.1f}s SPEAKER_{current_speaker}] {' '.join(current_words)}")

    return '\n'.join(lines)


def build_silence_summary(silence_map: dict) -> str:
    """
    Converts silence map to compact string.
    Example: "Silences: 2.1-2.8s, 5.0-5.4s, 11.2-12.0s"
    Only include silences > 0.3s.
    """
    silent_intervals = silence_map.get("silent_intervals", [])
    if not silent_intervals:
        return "No significant silences."
    
    silences = []
    for interval in silent_intervals:
        start = interval.get("start", 0.0)
        end = interval.get("end", 0.0)
        if end - start > 0.3:
            silences.append(f"{start:.1f}-{end:.1f}s")
            
    if not silences:
        return "No silences > 0.3s."
        
    return "Silences: " + ", ".join(silences)


def generate_edit_decisions(
    transcript: list[dict],
    speaker_segments: list[dict],
    silence_map: dict,
    video_metadata: dict,
    target_max_duration: float = 35.0
) -> dict:
    
    transcript_text = build_transcript_text(transcript)
    silence_summary = build_silence_summary(silence_map)
    duration = video_metadata.get('duration', 0.0)
    
    unique_speakers = set()
    for seg in speaker_segments:
        if 'speaker_id' in seg:
            unique_speakers.add(seg['speaker_id'])
    speaker_count = len(unique_speakers)

    prompt = EDITOR_PROMPT_TEMPLATE.format(
        target_max_duration=target_max_duration,
        transcript_text=transcript_text,
        silence_summary=silence_summary,
        duration=duration,
        speaker_count=speaker_count
    )

    try:
        client = get_editor_gemini_client()

        config = types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=2048,
            response_mime_type="application/json",
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config
        )

        raw_output = response.text

        try:
            if hasattr(response, 'usage_metadata'):
                logger.info(f"Gemini token usage: {response.usage_metadata}")
        except Exception:
            pass

        try:
            cleaned = raw_output.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            decisions = json.loads(cleaned)
            if "_reasoning" in decisions:
                logger.debug(f"Gemini Reasoning: {decisions['_reasoning']}")
            return decisions
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON. Raw output: {raw_output}")
            raise ValueError(f"Invalid JSON from Gemini: {str(e)}")

    except Exception as e:
        logger.error(f"Vertex AI API error: {str(e)}")
        raise


from typing import Dict, Any

def validate_edit_decisions(decisions: dict, video_duration: float) -> dict:
    """
    Sanitize and validate Gemini output before sending to frontend.
    - Clamp all timestamps to [0, video_duration]
    - Remove cuts where remove_from >= remove_to
    - Remove cuts shorter than 0.2 seconds
    - Remove cuts that overlap with each other (keep first)
    - Ensure hook_start is within [0, video_duration]
    - Clamp speed multipliers to [1.0, 1.20]
    - Sort cuts by remove_from ascending
    - Ensure commentary_cards.at is within [0, video_duration]
    - Keep _reasoning field in output (for logging purposes)
    Returns sanitized decisions dict.
    """
    validated: Dict[str, Any] = {}
    
    if "_reasoning" in decisions:
        validated["_reasoning"] = decisions["_reasoning"]
        
    hook_start = max(0.0, min(float(decisions.get("hook_start", 0.0)), video_duration))
    validated["hook_start"] = hook_start
    validated["hook_reason"] = decisions.get("hook_reason", "")[:100]
    validated["hook_score"] = max(0, min(int(decisions.get("hook_score", 0)), 100))
    
    raw_cuts = decisions.get("cuts", [])
    valid_cuts: list[Dict[str, Any]] = []
    for cut in raw_cuts:
        r_from = max(0.0, min(float(cut.get("remove_from", 0.0)), video_duration))
        r_to = max(0.0, min(float(cut.get("remove_to", 0.0)), video_duration))
        if r_to - r_from >= 0.2:
            valid_cuts.append({
                "remove_from": r_from,
                "remove_to": r_to,
                "reason": cut.get("reason", "unknown")
            })
            
    valid_cuts.sort(key=lambda x: x["remove_from"])
    
    non_overlapping_cuts: list[Dict[str, Any]] = []
    last_end = -1.0
    for cut in valid_cuts:
        if cut["remove_from"] >= last_end:
            non_overlapping_cuts.append(cut)
            last_end = cut["remove_to"]
            
    total_cut_duration = sum(c["remove_to"] - c["remove_from"] for c in non_overlapping_cuts)
    if total_cut_duration > video_duration * 0.6:
        logger.warning("Cuts would remove > 60% of content. Keeping only top 5 longest cuts.")
        sorted_by_duration = sorted(non_overlapping_cuts, key=lambda x: x["remove_to"] - x["remove_from"], reverse=True)
        import itertools
        non_overlapping_cuts = sorted(list(itertools.islice(sorted_by_duration, 5)), key=lambda x: x["remove_from"])
        
    validated["cuts"] = non_overlapping_cuts
    
    speed_sections = []
    for s in decisions.get("speed_sections", []):
        sf = max(0.0, min(float(s.get("from", 0.0)), video_duration))
        st = max(0.0, min(float(s.get("to", 0.0)), video_duration))
        if st > sf:
            mult = max(1.0, min(float(s.get("multiplier", 1.0)), 1.20))
            speed_sections.append({
                "from": sf,
                "to": st,
                "multiplier": mult
            })
    validated["speed_sections"] = speed_sections
    
    cards = []
    for c in decisions.get("commentary_cards", []):
        at = max(0.0, min(float(c.get("at", 0.0)), video_duration))
        dur = max(2.0, min(float(c.get("duration", 2.0)), 4.0))
        pos = c.get("position", "center")
        if pos not in ["top", "center", "bottom"]:
            pos = "center"
        cards.append({
            "text": c.get("text", "")[:40],
            "at": at,
            "duration": dur,
            "position": pos
        })
    validated["commentary_cards"] = cards
    
    validated["title_suggestion"] = decisions.get("title_suggestion", "")[:60]
    validated["description_suggestion"] = decisions.get("description_suggestion", "")
    
    est = float(decisions.get("total_duration_estimate", 0.0))
    if est > 35.0:
        logger.warning(f"total_duration_estimate {est} > target max duration 35.0")
    validated["total_duration_estimate"] = est
    
    return validated
