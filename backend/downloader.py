# backend/downloader.py

import os
import subprocess
import json
import time
from pathlib import Path

def download_video(url: str, job_id: str) -> tuple[str, str, str]:
    job_dir = Path("output") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = Path("cookies.txt")

    print(f"[Downloader] {job_id} için video bilgileri alınmaya çalışılıyor...")

    # ── HATA TOLERANSI: FORMAT VE BOT ODAKLI STRATEJİLER ──
    # Loglardan anladığımız üzere cookie'lerimiz bot korumasını geçiyor! 
    # Ancak karmaşık client taklitleri format uyuşmazlığı yaratıyor.
    strategies =[
        {
            "name": "Strateji 1: Varsayılan İstemci + Cookies (En güvenlisi)",
            "bypass_args": [],
            "use_cookies": True
        },
        {
            "name": "Strateji 2: Android İstemcisi + Cookies",
            "bypass_args": ["--extractor-args", "youtube:player_client=android"],
            "use_cookies": True
        },
        {
            "name": "Strateji 3: iOS İstemcisi + Cookies",
            "bypass_args":["--extractor-args", "youtube:player_client=ios"],
            "use_cookies": True
        }
    ]

    info = None
    video_title = "Bilinmeyen Video"
    success_strategy = None

    for attempt, strat in enumerate(strategies, 1):
        print(f"[Downloader] 🔄 Deneme {attempt}/3 - {strat['name']}")
        
        cookie_args = []
        if strat["use_cookies"] and cookie_path.exists() and cookie_path.stat().st_size > 0:
            cookie_args = ["--cookies", str(cookie_path)]
            
        # --dump-json sırasında format hatası (Requested format is not available)
        # almamak için arama formatını "best" olarak rahatlatıyoruz.
        info_cmd =["yt-dlp", "--no-warnings", "--dump-json", "-f", "best"] + cookie_args + strat["bypass_args"] + [url]
        
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
        raise RuntimeError(f"Video bilgileri alınamadı. Son hata: {info_result.stderr.strip()}")

    print(f"[Downloader] 📥 Video indiriliyor (Kazanan Strateji: {success_strategy['name']})...")
    
    # Formatı esnettik: "bestvideo+bestaudio/best" diyerek uzantı zorlamasını kaldırdık.
    # --merge-output-format mp4 sayesinde yt-dlp her halükarda onu mp4'e paketleyecek.
    mp4_cmd =[
        "yt-dlp", "--no-warnings",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(job_dir / "source.%(ext)s")
    ]
    
    if success_strategy["use_cookies"] and cookie_path.exists():
        mp4_cmd += ["--cookies", str(cookie_path)]
        
    mp4_cmd += success_strategy["bypass_args"] + [url]

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