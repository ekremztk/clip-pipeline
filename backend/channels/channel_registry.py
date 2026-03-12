"""
channel_registry.py — Dinamik Kanal Yöneticisi
Yeni kanal eklemek için sadece channels/<id>/config.py oluşturmak yeterlidir.
"""

import importlib
from typing import Optional

# Kayıtlı kanal ID'leri — yeni kanal ekleyince buraya ekle
REGISTERED_CHANNELS = [
    "speedy_cast",
]


def get_channel_ids() -> list[str]:
    """Tüm kayıtlı kanal ID'lerini döndürür."""
    return REGISTERED_CHANNELS.copy()


def get_channel_config(channel_id: str) -> Optional[object]:
    """
    Dinamik config yükler. channels/<channel_id>/config.py mevcut değilse
    speedy_cast'e düşer. Hiçbir zaman None döndürmez.
    """
    try:
        module = importlib.import_module(f"channels.{channel_id}.config")
        print(f"[Registry] ✅ '{channel_id}' config yüklendi.")
        return module
    except (ImportError, ModuleNotFoundError):
        print(f"[Registry] ⚠️ '{channel_id}' config bulunamadı, speedy_cast'e düşülüyor.")
        try:
            return importlib.import_module("channels.speedy_cast.config")
        except Exception as e:
            print(f"[Registry] ❌ speedy_cast fallback da başarısız: {e}")
            return None
