"""
Live smoke test for the GPT option on S05/S06.

Everything about this path is unit-tested except the one thing only a real call
can settle: whether settings.OPENAI_MODEL names a model the account can reach,
and whether its output survives the same JSON parser S05 already uses.

Run from anywhere, with OPENAI_API_KEY in backend/.env:

    python3 tools/smoke_test_gpt_step.py

Costs a few cents. Does not touch the database or any job.
"""
import sys
from pathlib import Path

# Both paths are resolved from this file, not the cwd, so the script runs from
# anywhere. dotenv's own search starts at the *caller's* directory — from
# tools/ that walks past backend/.env entirely and silently loads nothing.
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

# app/main.py does this before anything reads settings; settings resolves its
# class attributes at import time, so a standalone script must load it first or
# every key comes back empty.
from dotenv import load_dotenv

load_dotenv(BACKEND / ".env")

from app.config import settings
from app.services import claude_client as cc
from app.pipeline.json_parser import parse_json_object_response

SYSTEM = (
    "You are a professional short-form video editor specializing in viral clips. "
    "Return ONLY a valid JSON object. No markdown, no explanation outside the JSON."
)

# Shaped like S05's ask: a labeled transcript in, {timeline_map, candidates} out.
TRANSCRIPT = """[HOST 00:00:04] So you walked off the set. Just like that.
[GUEST 00:00:09] I did. Thirty years in this business and I had never done it.
[GUEST 00:00:15] But he said something about my daughter and I was done.
[HOST 00:00:22] What did the studio say?
[GUEST 00:00:25] They fined me. I paid it and I'd pay it again tomorrow.
[HOST 00:00:33] Anyway, let's talk about the new album."""

PROMPT = f"""Find the single strongest short-form clip in this transcript.

Return JSON exactly:
{{"timeline_map": [{{"start": 0, "end": 40, "summary": "..."}}],
  "candidates": [{{"candidate_id": 1, "recommended_start": 0.0,
                   "recommended_end": 0.0, "hook_text": "...", "reason": "..."}}]}}

TRANSCRIPT:
{TRANSCRIPT}"""


def main() -> int:
    if not settings.OPENAI_API_KEY:
        print("FAIL  OPENAI_API_KEY is not set")
        return 1

    print(f"model={settings.OPENAI_MODEL} effort={settings.OPENAI_REASONING_EFFORT}")
    cc.reset_claude_tokens()

    try:
        raw = cc.call_claude(
            content=[{"type": "text", "text": PROMPT}],
            system=SYSTEM,
            max_tokens=16000,
            allow_premium=True,
            model_choice=cc.GPT_CHOICE,
        )
    except Exception as e:
        print(f"FAIL  call raised: {e}")
        print("      If this says the model does not exist, set OPENAI_MODEL to the")
        print("      correct id — no code change is needed.")
        return 1

    print(f"PASS  call returned {len(raw)} chars")

    payload = parse_json_object_response(raw, log_prefix="[smoke]")
    candidates = (payload or {}).get("candidates") or []
    if not candidates:
        print("FAIL  parser produced no candidates — raw output follows:")
        print(raw[:800])
        return 1
    print(f"PASS  S05's parser read {len(candidates)} candidate(s)")
    print(f"      hook: {str(candidates[0].get('hook_text'))[:80]}")

    usage = cc.get_claude_tokens()
    if usage.get("provider") != "openai" or not usage.get("input_tokens"):
        print(f"FAIL  token accounting looks wrong: {usage}")
        return 1
    print(f"PASS  audit row would record: {usage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
