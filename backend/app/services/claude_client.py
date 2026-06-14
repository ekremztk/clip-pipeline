import time

import anthropic
from anthropic import AnthropicFoundry
from app.config import settings

BEDROCK_FALLBACK_MODEL = "us.anthropic.claude-opus-4-6-v1"


def _make_foundry_client() -> AnthropicFoundry | None:
    if settings.ANTHROPIC_FOUNDRY_API_KEY and settings.ANTHROPIC_FOUNDRY_RESOURCE:
        return AnthropicFoundry(
            api_key=settings.ANTHROPIC_FOUNDRY_API_KEY,
            resource=settings.ANTHROPIC_FOUNDRY_RESOURCE,
        )
    return None


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
) -> str:
    system_text = (
        system
        or "You are a ruthless viral clip quality analyst. "
           "Return only valid JSON. Never wrap output in markdown code blocks."
    )

    system_blocks = [
        {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if extra_system_blocks:
        system_blocks.extend(extra_system_blocks)

    messages = [{"role": "user", "content": content}]

    # Strategy: Foundry (claude-opus-4-8) first, Bedrock (claude-opus-4-6) fallback
    last_error = ""

    # --- Stage 1: Azure AI Foundry (primary) ---
    foundry_client = _make_foundry_client()
    if foundry_client:
        for attempt in range(2):
            try:
                print(
                    f"[ClaudeClient] Calling model={settings.CLAUDE_MODEL} "
                    f"provider=foundry attempt={attempt + 1}/2"
                )
                response = foundry_client.messages.create(
                    model=settings.CLAUDE_MODEL,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    thinking={"type": "adaptive"},
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
                last_error = f"rate_limit model={settings.CLAUDE_MODEL} provider=foundry"
                if attempt == 0:
                    print(
                        f"[ClaudeClient] Rate limit provider=foundry; "
                        f"sleeping 60s before one retry"
                    )
                    time.sleep(60)
                    continue
                print("[ClaudeClient] Rate limit exhausted on Foundry; falling back to Bedrock")
                break
            except Exception as e:
                last_error = f"error model={settings.CLAUDE_MODEL} provider=foundry: {e}"
                print(f"[ClaudeClient] Foundry error attempt={attempt + 1}/2: {e}")
                break

    # --- Stage 2: AWS Bedrock (fallback) ---
    bedrock_client = _make_bedrock_client()
    if bedrock_client:
        for attempt in range(2):
            try:
                print(
                    f"[ClaudeClient] Calling model={BEDROCK_FALLBACK_MODEL} "
                    f"provider=bedrock attempt={attempt + 1}/2"
                )
                response = bedrock_client.messages.create(
                    model=BEDROCK_FALLBACK_MODEL,
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
                last_error = f"rate_limit model={BEDROCK_FALLBACK_MODEL} provider=bedrock"
                if attempt == 0:
                    print(
                        f"[ClaudeClient] Rate limit provider=bedrock; "
                        f"sleeping 120s before one retry"
                    )
                    time.sleep(120)
                    continue
                print("[ClaudeClient] Rate limit exhausted on Bedrock")
                break
            except Exception as e:
                last_error = f"error model={BEDROCK_FALLBACK_MODEL} provider=bedrock: {e}"
                print(f"[ClaudeClient] Bedrock error attempt={attempt + 1}/2: {e}")
                break

    raise RuntimeError(
        "Claude call failed on all providers (Foundry → Bedrock) after bounded retries"
        + (f": {last_error}" if last_error else "")
    )
