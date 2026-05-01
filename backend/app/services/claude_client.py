import time
import anthropic
from app.config import settings

CLAUDE_MODEL_FALLBACK = "us.anthropic.claude-opus-4-6"


def _make_client() -> anthropic.AnthropicBedrock:
    return anthropic.AnthropicBedrock(
        aws_access_key=settings.AWS_BEDROCK_ACCESS_KEY,
        aws_secret_key=settings.AWS_BEDROCK_SECRET_KEY,
        aws_region=settings.AWS_BEDROCK_REGION,
    )


def call_claude(
    content: list,
    system: str | None = None,
    max_tokens: int = 16000,
    extra_system_blocks: list | None = None,
) -> str:
    """
    Calls Claude on AWS Bedrock with max thinking budget.
    Falls back to CLAUDE_MODEL_FALLBACK if primary model returns an error.
    Retries on rate limits: 60s, 120s, 180s (4 attempts).
    """
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

    models_to_try = [settings.CLAUDE_MODEL, CLAUDE_MODEL_FALLBACK]

    for model in models_to_try:
        client = _make_client()
        delays = [60, 120, 180]
        for attempt in range(4):
            try:
                print(f"[ClaudeClient] Calling model={model} attempt={attempt + 1}")
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    thinking={"type": "enabled", "budget_tokens": max_tokens - 1000},
                    messages=messages,
                    timeout=600.0,
                )

                usage = response.usage
                cache_read  = getattr(usage, "cache_read_input_tokens",  0) or 0
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

            except anthropic.RateLimitError as e:
                if attempt < 3:
                    delay = delays[attempt]
                    print(f"[ClaudeClient] Rate limit model={model} (attempt {attempt + 1}/4). Sleeping {delay}s...")
                    time.sleep(delay)
                else:
                    print(f"[ClaudeClient] Rate limit exhausted for model={model}, trying fallback...")
                    break
            except Exception as e:
                print(f"[ClaudeClient] Error model={model} attempt={attempt + 1}: {e}")
                # Non-rate-limit error (model unavailable etc.) → try fallback immediately
                break

    raise RuntimeError("Claude call failed on all models")
