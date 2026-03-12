"""
speedy_cast/config.py — Speedy Cast Clip Kanal Konfigürasyonu
Bu dosya analyzer.py tarafından channel_registry üzerinden dinamik yüklenir.
"""

CHANNEL_ID = "speedy_cast"
DISPLAY_NAME = "Speedy Cast Clip"

MIN_CLIP_DURATION = 15   # saniye
MAX_CLIP_DURATION = 35   # saniye

SYSTEM_PROMPT = """
CHANNEL: Speedy Cast Clip
CONTENT TYPE: Long-form podcast and talk-show clips (Turkish & English)
TARGET AUDIENCE: General audience interested in podcasts, interviews, discussions
VIRAL STYLE: Strong hooks, controversial opinions, emotional reveals, relatable moments
PRIORITY TRIGGERS: curiosity_gap, social_proof, emotional_spike, controversy
AVOID: Slow intros, mid-sentence cuts, low-energy monologues
"""
