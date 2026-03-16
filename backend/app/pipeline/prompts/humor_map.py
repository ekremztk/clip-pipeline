PROMPT = """You are analyzing a podcast transcript to find subtle moments of humor that audio energy analysis cannot detect.

Channel humor style: STYLE_PLACEHOLDER
Channel humor triggers: TRIGGERS_PLACEHOLDER

Focus specifically on these types of humor:
- Deadpan: absurd thing said in flat serious tone
- Dry wit: clever unexpected comment, usually one sentence
- Irony: saying the opposite of what is meant
- Unexpected honesty: admitting something embarrassingly true
- Host timing: question asked at exactly the right funny moment

RULES:
- Only include moments with confidence >= 0.5
- Return empty array if no humor found — do not force results
- Timestamp must be parsed from [MM:SS.s] format and converted to seconds (float)
- Output valid JSON array only, no markdown

SCHEMA FOR EACH ITEM IN THE ARRAY:
{
  "timestamp": float (seconds),
  "type": "deadpan" | "dry_wit" | "irony" | "unexpected_honesty" | "host_timing",
  "confidence": float (0.0-1.0),
  "note": "one sentence explaining why this is funny"
}

TRANSCRIPT:
TRANSCRIPT_PLACEHOLDER
"""
