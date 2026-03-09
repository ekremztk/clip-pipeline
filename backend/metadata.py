from pathlib import Path
from datetime import datetime

def write_metadata(clips_data: list[dict], job_id: str, video_title: str) -> str:
    job_dir = Path("output") / job_id
    meta_path = str(job_dir / "metadata.txt")

    now = datetime.now().strftime("%d %B %Y, %H:%M")
    lines = []

    # ── HEADER ──────────────────────────────────────────────────────
    lines += [
        "╔══════════════════════════════════════════════════════════════╗",
        "║                    CLIP PIPELINE — RAPOR                    ║",
        "╚══════════════════════════════════════════════════════════════╝",
        "",
        f"  📺  Kaynak Video  : {video_title}",
        f"  📅  Oluşturulma   : {now}",
        f"  🎬  Toplam Klip   : {len(clips_data)}",
        "",
    ]

    # ── AI RECOMMENDATION ───────────────────────────────────────────
    if clips_data and clips_data[0].get("recommendation"):
        lines += [
            "┌─────────────────────────────────────────────────────────────┐",
            "│  💡  AI TAVSİYESİ                                           │",
            "└─────────────────────────────────────────────────────────────┘",
            "",
            f"  {clips_data[0]['recommendation']}",
            "",
        ]

    # ── CLIPS SUMMARY TABLE ─────────────────────────────────────────
    lines += [
        "┌─────────────────────────────────────────────────────────────┐",
        "│  📊  ÖZET TABLO                                             │",
        "└─────────────────────────────────────────────────────────────┘",
        "",
        f"  {'#':<4} {'Score':<8} {'Süre':<18} {'Başlık'}",
        f"  {'─'*4} {'─'*8} {'─'*18} {'─'*30}",
    ]
    for i, clip in enumerate(clips_data):
        score = clip.get("score", "?")
        score_icon = "🟢" if (score != "?" and score >= 85) else "🟡" if (score != "?" and score >= 70) else "🔴"
        time_range = f"{format_time(clip['start_sec'])} → {format_time(clip['end_sec'])}"
        title_short = clip['title'][:40] + ("..." if len(clip['title']) > 40 else "")
        lines.append(f"  {i+1:<4} {score_icon} {score:<5} {time_range:<18} {title_short}")
    lines += ["", ""]

    # ── INDIVIDUAL CLIP REPORTS ─────────────────────────────────────
    for i, clip in enumerate(clips_data):
        score = clip.get("score", "N/A")
        score_bar = _score_bar(score)
        duration = clip['end_sec'] - clip['start_sec']

        lines += [
            "═" * 63,
            f"  KLIP {i+1}  ·  {clip['title']}",
            "═" * 63,
            "",
        ]

        # Score & timing block
        lines += [
            f"  ┌─ PERFORMANS ──────────────────────────────────────────┐",
            f"  │  Viral Skor    {score_bar}  {score}/100",
            f"  │  Zaman         {format_time(clip['start_sec'])} → {format_time(clip['end_sec'])}  ({duration:.0f} sn)",
            f"  │  Platform      YouTube Shorts / TikTok / Reels",
            f"  └────────────────────────────────────────────────────────┘",
            "",
        ]

        # Why selected
        if clip.get("why_selected"):
            lines += [
                "  🎯  NEDEN SEÇİLDİ",
                f"  {clip['why_selected']}",
                "",
            ]

        # Hook
        if clip.get("hook"):
            lines += [
                "  🎣  HOOK (İlk 2 Saniye)",
                f"  {clip['hook']}",
                "",
            ]

        # Audio highlights
        if clip.get("audio_highlights"):
            lines += [
                "  🎵  SES ANALİZİ",
                f"  {clip['audio_highlights']}",
                "",
            ]

        # Trim note
        trim = clip.get("trim_note", "none")
        if trim and trim.lower() != "none":
            lines += [
                "  ✂️   EDİT NOTU",
                f"  {trim}",
                "",
            ]

        # Content block
        lines += [
            "  ─" * 31,
            "",
            "  📌  YAYINLANACAK İÇERİK",
            "",
            f"  Başlık    :  {clip['title']}",
            "",
            "  Açıklama  :",
        ]
        # Word-wrap description at ~60 chars
        for chunk in _wrap(clip['description'], 60):
            lines.append(f"  {chunk}")
        lines += [
            "",
            "  Hashtag   :",
            f"  {clip['hashtags']}",
            "",
        ]

        # Transcript
        if clip.get("transcript"):
            lines += [
                "  ─" * 31,
                "",
                "  📝  TRANSKRİPT",
                "",
            ]
            for chunk in _wrap(clip['transcript'], 60):
                lines.append(f"  {chunk}")
            lines.append("")

        lines.append("")

    # ── FOOTER ──────────────────────────────────────────────────────
    lines += [
        "═" * 63,
        "  Clip Pipeline · Otomatik üretildi · speedy cast clip",
        "═" * 63,
    ]

    with open(meta_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return meta_path


def _score_bar(score) -> str:
    if score == "N/A" or score is None:
        return "░░░░░░░░░░"
    filled = round(score / 10)
    return "█" * filled + "░" * (10 - filled)


def _wrap(text: str, width: int) -> list[str]:
    """Simple word wrapper."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 <= width:
            current = (current + " " + word).strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else [text]


def format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"