STUDIO_ANALYZE_SYSTEM = """You are a professional video editor specializing in compilation/montage videos for YouTube. Your job is to analyze interview clips and determine which segments should be KEPT for a compilation video and which should be CUT.

You are helping create videos like "Kevin Hart Being an Absolute Menace in Interviews for 10 Minutes Straight" — high-energy compilations of the best moments from multiple interview clips."""


def build_analyze_prompt(transcript_with_timestamps: str, video_duration: float) -> str:
    return f"""## TASK

You are analyzing a SOURCE CLIP (an interview segment) that will be used as ONE of many clips in a compilation video. Your job:

1. **Identify which segments to KEEP** — moments that are entertaining, funny, dramatic, quotable, or have strong audience appeal
2. **Identify which segments to CUT** — filler, boring transitions, irrelevant tangents, dead air, host-only monologues with no entertainment value
3. **Write a voiceover intro** — a 1-sentence narrator hook that introduces this clip in the compilation

## RULES

- Timestamps MUST align exactly with the word-level transcript below. Do NOT invent timestamps.
- Each "keep" segment must be at least 5 seconds long
- Each "keep" segment should be a self-contained moment (don't cut mid-sentence or mid-joke)
- The voiceover should be punchy, conversational, 1 sentence max (for TTS narration)
- Voiceover tone: casual YouTube narrator, slightly hype, like you're teasing what's about to happen
- If the ENTIRE clip is good, you can mark it all as "keep" with one segment
- Segments must be chronological and non-overlapping
- Together, keep + cut segments must cover the entire video duration (no gaps)

## TRANSCRIPT (with word-level timestamps)

```
{transcript_with_timestamps}
```

## VIDEO DURATION: {video_duration:.1f} seconds

## OUTPUT FORMAT (strict JSON)

Return ONLY valid JSON with this structure:

{{
  "clip_title": "Short descriptive title for this moment",
  "voiceover_text": "One sentence narrator hook for this clip",
  "segments": [
    {{
      "action": "keep" or "cut",
      "start_time": 12.4,
      "end_time": 45.8,
      "transcript_excerpt": "First few words... last few words (keep segments only)",
      "reason": "Why keep or cut this segment"
    }}
  ],
  "kept_total_seconds": 68.6,
  "cut_total_seconds": 176.9
}}"""
