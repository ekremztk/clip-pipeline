"""
Message Router — determines if a chat message needs tool access.

Simple pattern matching to avoid unnecessary Gemini Pro tool-calling
for greetings, acknowledgments, and general questions.
"""

import re

DIRECT_PATTERNS = [
    r'^(merhaba|selam|hey|hi|hello|naber|nasılsın)',
    r'^(teşekkür|sağol|eyvallah|thanks|thank you)',
    r'^(tamam|ok|evet|anladım|güzel|harika|süper)',
    r'^(kimsin|ne yapabilirsin|nasıl çalışıyorsun)',
]

DATA_KEYWORDS = [
    'kaç', 'göster', 'analiz', 'kontrol', 'bak', 'pipeline', 'klip', 'clip',
    'hata', 'error', 'score', 'puan', 'maliyet', 'cost', 'durum', 'status',
    'son', 'istatistik', 'stats', 'performance', 'channel', 'kanal', 'job',
    'dna', 'hafıza', 'memory', 'öneri', 'recommendation', 'log', 'deploy',
    'test', 'forecast', 'tahmin', 'risk', 'kapasite', 'capacity', 'compare',
]


def should_use_tools(message: str) -> bool:
    """Return True if the message likely needs tool access, False for direct response."""
    msg = message.strip().lower()

    # Short messages: check patterns first
    if len(msg.split()) < 4:
        for pat in DIRECT_PATTERNS:
            if re.match(pat, msg):
                return False
        if not any(k in msg for k in DATA_KEYWORDS):
            return False

    return True
