"""
Message Router — determines if a chat message needs tool access.

Simple pattern matching to avoid unnecessary Gemini Pro tool-calling
for greetings, acknowledgments, and general questions.
"""

import re

# Only these SHORT messages skip tools entirely
DIRECT_PATTERNS = [
    r'^(merhaba|selam|hey|hi|hello|naber|nasılsın)[\s!?.]*$',
    r'^(teşekkür|sağol|eyvallah|thanks|thank you)[\s!?.]*$',
    r'^(tamam|ok|evet|anladım|güzel|harika|süper)[\s!?.]*$',
    r'^(kimsin|ne yapabilirsin|nasıl çalışıyorsun)[\s!?.]*$',
]

# Any of these → definitely use tools
TOOL_KEYWORDS = [
    'kaç', 'göster', 'analiz', 'kontrol', 'bak', 'incele', 'araştır', 'tara',
    'pipeline', 'klip', 'clip', 'hata', 'error', 'score', 'puan', 'skor',
    'maliyet', 'cost', 'durum', 'status', 'son', 'istatistik', 'stats',
    'performance', 'performans', 'channel', 'kanal', 'job', 'dna',
    'hafıza', 'memory', 'öneri', 'recommendation', 'log', 'deploy',
    'test', 'forecast', 'tahmin', 'risk', 'kapasite', 'capacity', 'compare',
    'karşılaştır', 'rapor', 'report', 'sistem', 'system', 'sağlık', 'health',
    'dosya', 'file', 'oku', 'read', 'veritabanı', 'database', 'sql',
    'prompt', 'a/b', 'editör', 'editor', 'yayın', 'publish',
    'tüm', 'hepsini', 'herşeyi', 'her şeyi', 'detaylı', 'derinlemesine',
    'neden', 'niye', 'sorun', 'problem', 'bug', 'fix', 'düzelt',
    'bağımlılık', 'dependency', 'cross', 'çapraz', 'modül', 'module',
]


def should_use_tools(message: str) -> bool:
    """Return True if the message likely needs tool access, False for direct response."""
    msg = message.strip().lower()

    # If any tool keyword exists → always use tools
    if any(k in msg for k in TOOL_KEYWORDS):
        return True

    # Only skip tools for very short greeting-like messages
    if len(msg.split()) <= 3:
        for pat in DIRECT_PATTERNS:
            if re.match(pat, msg):
                return False

    # Default: use tools (safer — let Gemini decide if it needs them)
    return True
