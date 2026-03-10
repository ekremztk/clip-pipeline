# backend/downloader.py

import os
import subprocess
import json
import time
from pathlib import Path

# --- SELF-HEALING (KENDİ KENDİNİ İYİLEŞTİRME) MEKANİZMASI ---
_YTDLP_UPDATED = False

def _ensure_ytdlp_updated():
    """
    Sistem her ayağa kalktığında yt-dlp'nin en güncel sürümde olduğundan
    emin olur. YouTube API değişikliklerine karşı otonom koruma sağlar.
    """
    global _YTDLP_UPDATED
    if not _YTDLP_UPDATED:
        print("[Downloader] 🛠️ Self-Healing: yt-dlp sürümü kontrol ediliyor ve güncelleniyor...")
        subprocess.run(["pip", "install", "--upgrade", "yt-dlp"], capture_output=True)
        _YTDLP_UPDATED = True
        print("[Downloader] 🛠️ Self-Healing: yt-dlp güncel!")

def download_video(url: str, job_id: str) -> tuple[str, str, str]:
    # İndirme işleminden önce daima güncel miyiz diye kontrol et (Sadece ilk çalışmada günceller)
    _ensure_ytdlp_updated()

    job_dir = Path("output") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = Path("cookies.txt")

    print(f"[Downloader] {job_id} için video bilgileri alınmaya çalışılıyor...")

    # ── HATA TOLERANSI: STRATEJİLER ──
    strategies =[
        {
            "name": "Strateji 1: Orijinal Karma (android,ios,web)",
            "bypass_args":["--extractor-args", "youtube:player_client=android,ios,web"]
        },
        {
            "name": "Strateji 2: Sadece Mobil İstemci (ios)",
            "bypass_args":["--extractor-args", "youtube:player_client=ios"]
        },
        {
            "name": "Strateji 3: Saf İstemci (Bypass Yok)",
            "bypass_args":[]
        }
    ]

    # Çerezleri ayarla
    cookie_args =[]
    if cookie_path.exists() and cookie_path.stat().st_size > 0:
        cookie_args = ["--cookies", str(cookie_path)]
        print("[Downloader] 🍪 cookies.txt bulundu, yetkilendirme kullanılıyor.")

    info = None
    video_title = "Bilinmeyen Video"
    success_strategy = None

    for attempt, strat in enumerate(strategies, 1):
        print(f"[Downloader] 🔄 Deneme {attempt}/3 - {strat['name']}")
        
        info_cmd =["yt-dlp", "--no-warnings", "--dump-json"] + cookie_args + strat["bypass_args"] + [url]
        info_result = subprocess.run(info_cmd, capture_output=True, text=True)
        
        if info_result.returncode == 0:
            try:
                info = json.loads(info_result.stdout)
                video_title = info.get("title", "Bilinmeyen Video")
                success_strategy = strat
                print(f"[Downloader] ✅ Bilgiler başarıyla çekildi. Başlık: {video_title}")
                break
            except json.JSONDecodeError:
                pass
        
        print(f"[Downloader] ⚠️ Deneme {attempt} başarısız: {info_result.stderr.strip()[:200]}...")
        time.sleep(2)

    if not success_strategy:
        raise RuntimeError(f"Video bilgileri alınamadı. Bot engeli veya sürüm uyuşmazlığı. Son hata: {info_result.stderr.strip()}")

    print(f"[Downloader] 📥 Video indiriliyor (Kazanan: {success_strategy['name']})...")
    
    # SENİN ÖNERDİĞİN ESNEK FORMAT DİZİLİMİ KULLANILIYOR
    mp4_cmd =[
        "yt-dlp", "--no-warnings",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(job_dir / "source.%(ext)s")
    ] + cookie_args + success_strategy["bypass_args"] + [url]

    mp4_result = subprocess.run(mp4_cmd, capture_output=True, text=True)
    if mp4_result.returncode != 0:
        raise RuntimeError(f"Video dosyası indirilemedi: {mp4_result.stderr}")

    mp4_path = str(job_dir / "source.mp4")
    if not os.path.exists(mp4_path):
        files = list(job_dir.glob("source.*"))
        if files:
            mp4_path = str(files[0])

    print("[Downloader] 🎵 Ses dosyası (MP3) ayrıştırılıyor...")
    mp3_path = str(job_dir / "audio.mp3")
    mp3_cmd =[
        "ffmpeg", "-y", "-i", mp4_path,
        "-q:a", "0", "-map", "a",
        mp3_path
    ]
    
    mp3_result = subprocess.run(mp3_cmd, capture_output=True, text=True)
    if mp3_result.returncode != 0:
         raise RuntimeError(f"Ses ayrıştırılamadı: {mp3_result.stderr}")

    print(f"[Downloader] 🎉 İndirme ve ayrıştırma tamamlandı: {video_title}")
    return mp4_path, mp3_path, video_title