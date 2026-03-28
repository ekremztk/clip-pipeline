from typing import Optional
import re


def extract_guest_name(title: str) -> Optional[str]:
    """
    Video başlığından konuk adını çıkarmaya çalışır.

    Tanınan kalıplar:
    - "ft. {Name}" veya "feat. {Name}"
    - "with {Name}"
    - "w/ {Name}"
    - "{Name} | Podcast Name"
    - "{Name} - Topic"
    - "interviews {Name}"
    - "sits down with {Name}"
    - "{Host} & {Guest}"
    - "#{Number} {Name}"  (podcast episode formatı)
    - "{Name} on {Topic}"

    Args:
        title: YouTube video başlığı

    Returns:
        Tahmin edilen konuk adı veya None
    """
    raise NotImplementedError("TODO")
