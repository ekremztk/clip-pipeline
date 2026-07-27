import os
import time

import anthropic
from app.config import settings

BEDROCK_MODEL = "us.anthropic.claude-opus-4-6-v1"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")


def _make_anthropic_client() -> anthropic.Anthropic | None:
    """First-party Anthropic API. Returns None unless ANTHROPIC_API_KEY is set,
    so an unconfigured deploy falls through to Bedrock unchanged."""
    key = os.getenv("ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=key) if key else None


_premium_user_cache: dict[str, bool] = {}


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
) -> str:
    """
    allow_premium gates the first-party Anthropic model. It defaults to False so
    any caller that does not explicitly opt in — including every client job —
    runs on Bedrock.
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

    last_error = ""

    # --- Anthropic API (used only when ANTHROPIC_API_KEY is set) ---
    # Opus 5 rejects budget_tokens and thinks by default, so max_tokens must
    # cover thinking + text together — hence the doubled ceiling.
    anthropic_client = _make_anthropic_client() if allow_premium else None
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
        for attempt in range(3):
            try:
                print(
                    f"[ClaudeClient] Calling model={BEDROCK_MODEL} "
                    f"provider=bedrock attempt={attempt + 1}/3"
                )
                response = bedrock_client.messages.create(
                    model=BEDROCK_MODEL,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    thinking={"type": "enabled", "budget_tokens": 10000},
                    messages=messages,
                    timeout=600.0,
                )

                usage = response.usage
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
