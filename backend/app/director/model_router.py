"""
Director Model Router — selects Flash or Pro based on message complexity.
Flash is cheaper and faster for simple responses. Pro is required for tool calling.
"""

from app.config import settings

FLASH_PATTERNS = [
    "özetle", "çevir", "düzenle", "düzelt", "format", "listele",
    "summarize", "translate", "list", "quick"
]


def select_model(message: str, force_tools: bool = False) -> str:
    """Select Flash or Pro based on message complexity."""
    if force_tools:
        return settings.GEMINI_MODEL_PRO  # Tool calling always uses Pro
    msg_lower = message.lower()
    if len(message.split()) < 30 and any(p in msg_lower for p in FLASH_PATTERNS):
        return settings.GEMINI_MODEL_FLASH
    return settings.GEMINI_MODEL_PRO
