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
) -> str:
    """
    Calls Claude with a pre-built content array (text + images interleaved).
    content: list of Anthropic content blocks (text / image dicts)
    Retries on rate limits: 30s, 60s, then raise RuntimeError.
    """
    client = get_claude_client()

    system_prompt = (
        system
        or "You are a ruthless viral clip quality analyst. "
           "Return only valid JSON. Never wrap output in markdown code blocks."
    )
    messages = [{"role": "user", "content": content}]

    delays = [30, 60]
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
            )
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
