import hashlib
import os
import time

import anthropic
from app.config import settings

BEDROCK_MODEL = "us.anthropic.claude-opus-4-6-v1"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")

# The value the UI and jobs route use to pin a step to OpenAI. Kept in the
# dashed style of the Claude choices ("opus-4-6") so the allowlists read alike.
GPT_CHOICE = "gpt-6-astra"


def _make_anthropic_client() -> anthropic.Anthropic | None:
    """First-party Anthropic API. Returns None unless ANTHROPIC_API_KEY is set,
    so an unconfigured deploy falls through to Bedrock unchanged."""
    key = os.getenv("ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=key) if key else None


_premium_user_cache: dict[str, bool] = {}

# Per-step token accounting. The orchestrator used to read Gemini's accumulator
# around the S05 call, which has run on Claude since April — so every audited
# run recorded 0 input and 0 output tokens and the cost of the two most
# expensive steps was invisible.
_token_accumulator: dict = {}


def reset_claude_tokens() -> None:
    _token_accumulator.clear()


def get_claude_tokens() -> dict:
    """Totals since the last reset. Empty dict when no Claude call was made."""
    return dict(_token_accumulator) if _token_accumulator else {}


def _record_usage(model: str, provider: str, usage) -> None:
    acc = _token_accumulator
    acc["model"] = model
    acc["provider"] = provider
    acc["calls"] = acc.get("calls", 0) + 1
    for field, key in (
        ("input_tokens", "input_tokens"),
        ("output_tokens", "output_tokens"),
        ("cache_read_input_tokens", "cache_read_tokens"),
        ("cache_creation_input_tokens", "cache_write_tokens"),
    ):
        acc[key] = acc.get(key, 0) + (getattr(usage, field, 0) or 0)


def is_premium_user(user_id: str | None) -> bool:
    """
    True only for accounts in admin_users. The first-party Anthropic key is
    billed to the platform owner, so client jobs must never reach it — they
    run on Bedrock, which is covered by free credits.

    Fails closed: any lookup error returns False and the job uses Bedrock.
    """
    if not user_id:
        return False
    uid = str(user_id)
    if uid in _premium_user_cache:
        return _premium_user_cache[uid]

    allowed = False
    try:
        from app.services.supabase_client import get_client

        res = get_client().table("admin_users").select("user_id").eq("user_id", uid).execute()
        allowed = bool(res.data)
    except Exception as e:
        print(f"[ClaudeClient] admin lookup failed for {uid}, using Bedrock: {e}")

    _premium_user_cache[uid] = allowed
    return allowed


def _blocks_to_text(blocks: list) -> str:
    """Flattens Anthropic content blocks into one string. Every caller passes
    text-only blocks; anything else is skipped rather than crashing the run."""
    parts = []
    for block in blocks or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text") or ""
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _record_openai_usage(model: str, usage) -> None:
    """OpenAI reports the same two totals under the same names but nests the
    cache counters, so the Anthropic recorder would silently log zero for them.
    Writes the same accumulator keys the audit log already reads, plus
    reasoning_tokens — at medium effort that is most of the output bill and it
    is the number this experiment exists to compare."""
    acc = _token_accumulator
    acc["model"] = model
    acc["provider"] = "openai"
    acc["calls"] = acc.get("calls", 0) + 1
    in_details = getattr(usage, "input_tokens_details", None)
    out_details = getattr(usage, "output_tokens_details", None)
    for key, value in (
        ("input_tokens", getattr(usage, "input_tokens", 0)),
        ("output_tokens", getattr(usage, "output_tokens", 0)),
        ("cache_read_tokens", getattr(in_details, "cached_tokens", 0)),
        ("cache_write_tokens", getattr(in_details, "cache_write_tokens", 0)),
        ("reasoning_tokens", getattr(out_details, "reasoning_tokens", 0)),
    ):
        acc[key] = acc.get(key, 0) + (value or 0)


def _call_openai(system_blocks: list, content: list, max_tokens: int) -> str:
    """
    Admin-only third option for S05/S06, pinned by model_choice == GPT_CHOICE.

    Deliberately has NO fallback to Bedrock. The point of this path is to judge
    GPT's clip selection against Claude's, and a silent fallback would hand back
    Bedrock's picks under GPT's name — the comparison would be worthless and the
    audit row would disagree with what the operator thinks they measured. A
    missing key or an exhausted retry raises instead.

    The prompt is not adapted for GPT: same system text, same user content, same
    downstream JSON parser. Only the model changes, which is what makes the two
    runs comparable.
    """
    import openai

    if not settings.OPENAI_API_KEY:
        raise RuntimeError(
            f"model_choice={GPT_CHOICE} was selected but OPENAI_API_KEY is not set. "
            "Refusing to silently run this step on another provider."
        )

    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    model = settings.OPENAI_MODEL

    # system_blocks arrives as [system_prompt, *extra_system_blocks]; S06 puts the
    # full labeled transcript in the extras and resends it on every batch. Joining
    # them in order into `instructions` keeps that transcript at the front of the
    # prompt, which is where OpenAI's automatic prefix caching can reach it — the
    # same reason the Anthropic path puts its cache breakpoint on the last block.
    instructions = _blocks_to_text(system_blocks)
    user_input = _blocks_to_text(content)

    # A stable key routes S06's batches to the same cached prefix. Derived from
    # the instructions so it needs no new plumbing through the call signature.
    cache_key = "prognot-" + hashlib.sha256(instructions.encode()).hexdigest()[:16]

    # Reasoning tokens are drawn from this ceiling, exactly like thinking tokens
    # on the Claude paths. S06.5 asks for 4000, which medium effort can spend on
    # reasoning alone and return an empty message — so give the same headroom the
    # Anthropic path gives.
    budget = max(max_tokens * 2, 32000)

    last_error = ""
    for attempt in range(3):
        try:
            print(
                f"[ClaudeClient] Calling model={model} provider=openai "
                f"effort={settings.OPENAI_REASONING_EFFORT} "
                f"max_output={budget} attempt={attempt + 1}/3"
            )
            response = client.responses.create(
                model=model,
                instructions=instructions,
                input=user_input,
                max_output_tokens=budget,
                reasoning={"effort": settings.OPENAI_REASONING_EFFORT},
                prompt_cache_key=cache_key,
                timeout=900.0,
            )

            usage = response.usage
            if usage:
                _record_openai_usage(model, usage)
                in_details = getattr(usage, "input_tokens_details", None)
                out_details = getattr(usage, "output_tokens_details", None)
                print(
                    f"[ClaudeClient] Tokens — in: {usage.input_tokens}, "
                    f"out: {usage.output_tokens}, "
                    f"reasoning: {getattr(out_details, 'reasoning_tokens', 0) or 0}, "
                    f"cache_read: {getattr(in_details, 'cached_tokens', 0) or 0}"
                )

            # Truncation returns whatever was written so far, which for these
            # callers is half a JSON object. Say so, rather than letting the
            # parser report a malformed response and hide the real cause.
            if response.status == "incomplete":
                reason = getattr(response.incomplete_details, "reason", "unknown")
                raise RuntimeError(f"response incomplete (reason={reason}, budget={budget})")

            text = response.output_text or ""
            if not text.strip():
                raise RuntimeError("empty response text")
            return text

        except openai.RateLimitError:
            last_error = f"rate_limit model={model} provider=openai"
            if attempt < 2:
                delay = 60 if attempt == 0 else 120
                print(f"[ClaudeClient] Rate limit provider=openai; sleeping {delay}s")
                time.sleep(delay)
                continue
            break
        except Exception as e:
            last_error = f"error model={model} provider=openai: {e}"
            print(f"[ClaudeClient] OpenAI error attempt={attempt + 1}/3: {e}")
            if attempt < 2:
                time.sleep(5)
                continue
            break

    raise RuntimeError(f"OpenAI call failed after bounded retries: {last_error}")


def _make_bedrock_client() -> anthropic.AnthropicBedrock | None:
    if settings.AWS_BEDROCK_ACCESS_KEY and settings.AWS_BEDROCK_SECRET_KEY:
        return anthropic.AnthropicBedrock(
            aws_access_key=settings.AWS_BEDROCK_ACCESS_KEY,
            aws_secret_key=settings.AWS_BEDROCK_SECRET_KEY,
            aws_region=settings.AWS_BEDROCK_REGION,
        )
    return None


def call_claude(
    content: list,
    system: str | None = None,
    max_tokens: int = 16000,
    extra_system_blocks: list | None = None,
    allow_premium: bool = False,
    model_choice: str | None = None,
) -> str:
    """
    allow_premium gates the first-party Anthropic model. It defaults to False so
    any caller that does not explicitly opt in — including every client job —
    runs on Bedrock.

    model_choice is the per-step admin override: "opus-5" pins this call to the
    Anthropic API, "opus-4-6" pins it to Bedrock, GPT_CHOICE pins it to OpenAI,
    None keeps the old behaviour. It narrows what allow_premium permits and never
    widens it — a client job carrying "opus-5" still lands on Bedrock, because
    allow_premium is False, and the same gate keeps client jobs off the OpenAI
    key, which is billed to the platform owner just as the Anthropic one is.
    """
    # Both current callers (S05, S06) pass their own system prompt; this is the
    # fallback for any future caller.
    system_text = (
        system
        or "You are a professional short-form video editor working on clips cut from "
           "long-form talk shows and interviews. "
           "Return only valid JSON. Never wrap output in markdown code blocks."
    )

    system_blocks = [{"type": "text", "text": system_text}]
    if extra_system_blocks:
        system_blocks.extend(extra_system_blocks)

    # Caching is a prefix match, so the breakpoint belongs on the LAST system
    # block — that caches the system prompt *and* the full transcript S06
    # resends on every batch. On the first block it only covered ~30 tokens,
    # under the minimum cacheable prefix, so nothing was ever cached.
    system_blocks[-1] = {**system_blocks[-1], "cache_control": {"type": "ephemeral"}}

    messages = [{"role": "user", "content": content}]

    # --- OpenAI (admin-only, explicitly pinned, no fallback) ---
    # Sits ahead of the Claude branches and returns or raises, so a GPT-pinned
    # step can never quietly complete on Bedrock. See _call_openai for why.
    if allow_premium and model_choice == GPT_CHOICE:
        return _call_openai(system_blocks, content, max_tokens)

    last_error = ""

    # --- Anthropic API (used only when ANTHROPIC_API_KEY is set) ---
    # Opus 5 rejects budget_tokens and thinks by default, so max_tokens must
    # cover thinking + text together — hence the doubled ceiling.
    use_anthropic = allow_premium and model_choice != "opus-4-6"
    anthropic_client = _make_anthropic_client() if use_anthropic else None
    if anthropic_client:
        for attempt in range(3):
            try:
                print(
                    f"[ClaudeClient] Calling model={ANTHROPIC_MODEL} "
                    f"provider=anthropic attempt={attempt + 1}/3"
                )
                response = anthropic_client.messages.create(
                    model=ANTHROPIC_MODEL,
                    max_tokens=max(max_tokens * 2, 32000),
                    system=system_blocks,
                    thinking={"type": "adaptive"},
                    output_config={"effort": "high"},
                    messages=messages,
                    timeout=900.0,
                )

                usage = response.usage
                _record_usage(ANTHROPIC_MODEL, "anthropic", usage)
                print(
                    f"[ClaudeClient] Tokens — in: {usage.input_tokens}, "
                    f"out: {usage.output_tokens}, "
                    f"cache_read: {getattr(usage, 'cache_read_input_tokens', 0) or 0}"
                )

                if response.stop_reason == "refusal":
                    last_error = f"refusal model={ANTHROPIC_MODEL}"
                    print("[ClaudeClient] Refusal; falling through to Bedrock")
                    break

                for block in response.content:
                    if block.type == "text":
                        return block.text

                print("[ClaudeClient] Warning: no text block in response")
                return ""

            except anthropic.RateLimitError:
                last_error = f"rate_limit model={ANTHROPIC_MODEL} provider=anthropic"
                if attempt < 2:
                    delay = 60 if attempt == 0 else 120
                    print(f"[ClaudeClient] Rate limit; sleeping {delay}s")
                    time.sleep(delay)
                    continue
                break
            except Exception as e:
                last_error = f"error model={ANTHROPIC_MODEL} provider=anthropic: {e}"
                print(f"[ClaudeClient] Anthropic error attempt={attempt + 1}/3: {e}")
                break

    # --- AWS Bedrock (default provider, and fallback if the above fails) ---
    bedrock_client = _make_bedrock_client()
    if bedrock_client:
        # Thinking and text share max_tokens, so the budget cannot exceed it.
        # It was pinned at 10000 while callers pass their own ceiling: S05 and
        # S06 ask for 16000 and are fine, S06.5 asks for 4000 and every call was
        # rejected outright. Scale the budget to the caller instead, and drop
        # thinking altogether when there is not enough room for the minimum.
        thinking_budget = min(10000, int(max_tokens * 0.7))
        thinking_arg = (
            {"type": "enabled", "budget_tokens": thinking_budget}
            if thinking_budget >= 1024
            else {"type": "disabled"}
        )
        for attempt in range(3):
            try:
                print(
                    f"[ClaudeClient] Calling model={BEDROCK_MODEL} "
                    f"provider=bedrock attempt={attempt + 1}/3 "
                    f"max_tokens={max_tokens} thinking={thinking_arg['type']}"
                    + (f" budget={thinking_budget}" if thinking_budget >= 1024 else "")
                )
                response = bedrock_client.messages.create(
                    model=BEDROCK_MODEL,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    thinking=thinking_arg,
                    messages=messages,
                    timeout=600.0,
                )

                usage = response.usage
                _record_usage(BEDROCK_MODEL, "bedrock", usage)
                cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
                cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
                if cache_read or cache_write:
                    print(f"[ClaudeClient] Cache — read: {cache_read}, write: {cache_write} tokens")

                block_types = [block.type for block in response.content]
                print(f"[ClaudeClient] Response blocks: {block_types}")
                for block in response.content:
                    if block.type == "text":
                        return block.text

                print("[ClaudeClient] Warning: no text block in response")
                return ""

            except anthropic.RateLimitError:
                last_error = f"rate_limit model={BEDROCK_MODEL} provider=bedrock"
                if attempt < 2:
                    delay = 60 if attempt == 0 else 120
                    print(
                        f"[ClaudeClient] Rate limit provider=bedrock; "
                        f"sleeping {delay}s before retry"
                    )
                    time.sleep(delay)
                    continue
                print("[ClaudeClient] Rate limit exhausted on Bedrock after 3 attempts")
                break
            except Exception as e:
                last_error = f"error model={BEDROCK_MODEL} provider=bedrock: {e}"
                print(f"[ClaudeClient] Bedrock error attempt={attempt + 1}/3: {e}")
                break

    raise RuntimeError(
        "Claude call failed on AWS Bedrock after bounded retries"
        + (f": {last_error}" if last_error else "")
    )
