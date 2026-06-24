import time

import anthropic
from app.config import settings

BEDROCK_MODEL = "us.anthropic.claude-opus-4-6-v1"


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

    last_error = ""

    # --- AWS Bedrock (primary and only provider) ---
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
