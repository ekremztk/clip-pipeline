import time
import threading
from dataclasses import dataclass

import anthropic
from app.config import settings

CLAUDE_MODEL_FALLBACK = "us.anthropic.claude-opus-4-6-v1"

_account_lock = threading.Lock()
_account_cursor = 0


@dataclass(frozen=True)
class BedrockAccount:
    label: str
    access_key: str
    secret_key: str
    region: str


def _configured_accounts() -> list[BedrockAccount]:
    accounts: list[BedrockAccount] = []
    if settings.AWS_BEDROCK_ACCESS_KEY and settings.AWS_BEDROCK_SECRET_KEY:
        accounts.append(BedrockAccount(
            label="primary",
            access_key=settings.AWS_BEDROCK_ACCESS_KEY,
            secret_key=settings.AWS_BEDROCK_SECRET_KEY,
            region=settings.AWS_BEDROCK_REGION,
        ))
    if settings.AWS_BEDROCK_ACCESS_KEY_2 and settings.AWS_BEDROCK_SECRET_KEY_2:
        accounts.append(BedrockAccount(
            label="secondary",
            access_key=settings.AWS_BEDROCK_ACCESS_KEY_2,
            secret_key=settings.AWS_BEDROCK_SECRET_KEY_2,
            region=settings.AWS_BEDROCK_REGION_2,
        ))
    return accounts


def _ordered_accounts() -> list[BedrockAccount]:
    """Return configured Bedrock accounts in round-robin order."""
    global _account_cursor
    accounts = _configured_accounts()
    if len(accounts) <= 1:
        return accounts
    with _account_lock:
        start = _account_cursor % len(accounts)
        _account_cursor += 1
    return accounts[start:] + accounts[:start]


def _make_client(account: BedrockAccount) -> anthropic.AnthropicBedrock:
    return anthropic.AnthropicBedrock(
        aws_access_key=account.access_key,
        aws_secret_key=account.secret_key,
        aws_region=account.region,
    )


def _model_sequence() -> list[str]:
    models = [settings.CLAUDE_MODEL, CLAUDE_MODEL_FALLBACK]
    deduped: list[str] = []
    for model in models:
        if model and model not in deduped:
            deduped.append(model)
    return deduped


def call_claude(
    content: list,
    system: str | None = None,
    max_tokens: int = 16000,
    extra_system_blocks: list | None = None,
) -> str:
    """
    Calls Claude on AWS Bedrock with max thinking budget.
    Uses configured Bedrock accounts in round-robin order.
    On rate limits, retries the same account once, then tries the next account.
    Falls back to CLAUDE_MODEL_FALLBACK if the primary model returns an error.
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

    models_to_try = _model_sequence()
    if not _configured_accounts():
        raise RuntimeError("No AWS Bedrock account is configured")

    last_error = ""
    for model in models_to_try:
        is_primary = model == settings.CLAUDE_MODEL
        retry_delay = 60 if is_primary else 120
        for account in _ordered_accounts():
            for attempt in range(2):
                try:
                    print(
                        f"[ClaudeClient] Calling model={model} "
                        f"account={account.label} attempt={attempt + 1}/2"
                    )
                    is_fallback = model == CLAUDE_MODEL_FALLBACK
                    thinking_config = (
                        {"type": "enabled", "budget_tokens": 10000}
                        if is_fallback
                        else {"type": "adaptive"}
                    )
                    client = _make_client(account)
                    response = client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        system=system_blocks,
                        thinking=thinking_config,
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
                    last_error = f"rate_limit model={model} account={account.label}"
                    if attempt == 0:
                        print(
                            f"[ClaudeClient] Rate limit model={model} account={account.label}; "
                            f"sleeping {retry_delay}s before one retry"
                        )
                        time.sleep(retry_delay)
                        continue
                    print(
                        f"[ClaudeClient] Rate limit exhausted model={model} "
                        f"account={account.label}; trying next account"
                    )
                    break
                except Exception as e:
                    last_error = f"error model={model} account={account.label}: {e}"
                    print(
                        f"[ClaudeClient] Error model={model} "
                        f"account={account.label} attempt={attempt + 1}/2: {e}"
                    )
                    break

    raise RuntimeError(
        "Claude call failed on all configured models/accounts after bounded retries"
        + (f": {last_error}" if last_error else "")
    )
