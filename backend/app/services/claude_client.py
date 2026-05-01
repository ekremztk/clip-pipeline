import time
import anthropic
from app.config import settings

_client: anthropic.AnthropicBedrock | None = None


def get_claude_client() -> anthropic.AnthropicBedrock:
    global _client
    if _client is None:
        _client = anthropic.AnthropicBedrock(
            aws_access_key=settings.AWS_BEDROCK_ACCESS_KEY,
            aws_secret_key=settings.AWS_BEDROCK_SECRET_KEY,
            aws_region=settings.AWS_BEDROCK_REGION,
        )
        print(f"[ClaudeClient] Initialized (Bedrock). Model: {settings.CLAUDE_MODEL}")
    return _client


def call_claude(
    content: list,
    system: str | None = None,
    max_tokens: int = 16000,
    extra_system_blocks: list | None = None,
) -> str:
    """
    Calls Claude on AWS Bedrock with adaptive thinking.

    content: list of Anthropic content blocks (text / image dicts)
    system: system prompt text
    extra_system_blocks: additional cached system blocks appended after main system

    Retries on rate limits: 30s, 60s, then raise RuntimeError.
    """
    client = get_claude_client()

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

    delays = [60, 120, 180]
    for attempt in range(4):
        try:
            response = client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_blocks,
                thinking={"type": "adaptive"},
                messages=messages,
                timeout=600.0,
            )

            usage = response.usage
            cache_read  = getattr(usage, "cache_read_input_tokens",  0) or 0
            cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
            if cache_read or cache_write:
                print(f"[ClaudeClient] Cache — read: {cache_read} tokens, write: {cache_write} tokens")

            # Extract text block — thinking blocks come first, skip them
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
                print(f"[ClaudeClient] Rate limit (attempt {attempt + 1}/4). Sleeping {delay}s...")
                time.sleep(delay)
            else:
                raise RuntimeError(f"Claude rate limit exhausted after 4 attempts: {e}")
        except Exception as e:
            print(f"[ClaudeClient] Error on attempt {attempt + 1}: {e}")
            raise

    raise RuntimeError("Claude call failed — unreachable")
