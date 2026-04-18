import time
import anthropic
from app.config import settings

_client: anthropic.Anthropic | None = None


def get_claude_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set in environment.")
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        print(f"[ClaudeClient] Initialized. Model: {settings.CLAUDE_MODEL}")
    return _client


def call_claude(
    content: list,
    system: str | None = None,
    max_tokens: int = 8000,
    extra_system_blocks: list | None = None,
) -> str:
    """
    Calls Claude with a pre-built content array (text + images interleaved).
    content: list of Anthropic content blocks (text / image dicts)
    extra_system_blocks: additional cached system blocks (e.g. full transcript) appended after main system.
    Retries on rate limits: 30s, 60s, then raise RuntimeError.

    The system prompt is sent as a cacheable content block (cache_control ephemeral).
    Subsequent batches within the 5-minute TTL window pay ~10% of normal input token cost.
    """
    client = get_claude_client()

    system_text = (
        system
        or "You are a ruthless viral clip quality analyst. "
           "Return only valid JSON. Never wrap output in markdown code blocks."
    )
    # Prompt caching: pass system as a list with cache_control so Anthropic caches it.
    # Cache writes cost the same as regular tokens; cache reads cost ~10%.
    # This means batches 2+ in the same job benefit automatically within the 5-min TTL.
    system_blocks = [
        {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    # Append extra cacheable system blocks (e.g., full labeled transcript)
    if extra_system_blocks:
        system_blocks.extend(extra_system_blocks)

    messages = [{"role": "user", "content": content}]

    delays = [30, 60]
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_blocks,
                messages=messages,
                timeout=300.0,
            )
            usage = response.usage
            cache_read  = getattr(usage, "cache_read_input_tokens",  0) or 0
            cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
            if cache_read or cache_write:
                print(f"[ClaudeClient] Cache — read: {cache_read} tokens, write: {cache_write} tokens")
            return response.content[0].text
        except anthropic.RateLimitError as e:
            if attempt < 2:
                delay = delays[attempt]
                print(f"[ClaudeClient] Rate limit (attempt {attempt + 1}/3). Sleeping {delay}s...")
                time.sleep(delay)
            else:
                raise RuntimeError(f"Claude rate limit exhausted after 3 attempts: {e}")
        except Exception as e:
            print(f"[ClaudeClient] Error on attempt {attempt + 1}: {e}")
            raise

    raise RuntimeError("Claude call failed — unreachable")
