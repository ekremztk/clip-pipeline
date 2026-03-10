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

    # ── HATA TOLERANSI: 3 FARKLI İNDİRME STRATEJİSİ ──
    strategies =[
        {
            "name": "Strateji 1: Smart TV & Web İstemcisi + Cookies",
            "bypass_args":["--extractor-args", "youtube:player_client=tv,web,android"],
            "use_cookies": True
        },
        {
            "name": "Strateji 2: Mobil/Creator İstemcisi (Cookies İPTAL + Cache Temizliği)",
            "bypass_args":["--extractor-args", "youtube:player_client=ios,android_creator,mweb", "--rm-cache-dir"],
            "use_cookies": False
        },
        {
            "name": "Strateji 3: Agresif Bypass (Varsayılan + Geo Bypass)",
            "bypass_args":["--extractor-args", "youtube:player_client=default", "--geo-bypass", "--rm-cache-dir"],
            "use_cookies": False
        }
    ]

    info = None
    video_title = "Bilinmeyen Video"
    success_strategy = None

    # Stratejileri sırayla dene
    for attempt, strat in enumerate(strategies, 1):
        print(f"[Downloader] 🔄 Deneme {attempt}/3 - {strat['name']}")
        
        cookie_args = []
        if strat["use_cookies"] and cookie_path.exists() and cookie_path.stat().st_size > 0:
            cookie_args =["--cookies", str(cookie_path)]
            
        info_cmd =["yt-dlp", "--no-warnings", "--dump-json"] + cookie_args + strat["bypass_args"] + [url]
        
        info_result = subprocess.run(info_cmd, capture_output=True, text=True)
        
        if info_result.returncode == 0:
            try:
                info = json.loads(info_result.stdout)
                video_title = info.get("title", "Bilinmeyen Video")
                success_strategy = strat
                print(f"[Downloader] ✅ Bilgiler başarıyla çekildi. Başlık: {video_title}")
                break  # Başarılı olunca döngüden çık
            except json.JSONDecodeError:
                pass
        
        # Başarısız olursa logla ve 2 saniye bekleyip diğer stratejiye geç
        print(f"[Downloader] ⚠️ Deneme {attempt} başarısız: {info_result.stderr.strip()[:200]}...")
        time.sleep(2)

    # Eğer 3 strateji de patlarsa hata fırlat (Frontend'e düşecek)
    if not success_strategy:
        raise RuntimeError(f"Bot engeli aşılamadı. Son hata: {info_result.stderr.strip()}")

    print(f"[Downloader] 📥 Video indiriliyor (Kazanan Strateji: {success_strategy['name']})...")
    
    # Videoyu kazanan stratejinin argümanlarıyla indir
    # Formatta ekstra güvenlik: 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    mp4_cmd =[
        "yt-dlp", "--no-warnings",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(job_dir / "source.%(ext)s")
    ]
    
    if success_strategy["use_cookies"] and cookie_path.exists():
        mp4_cmd +=["--cookies", str(cookie_path)]
        
    mp4_cmd += success_strategy["bypass_args"] + [url]

    mp4_result = subprocess.run(mp4_cmd, capture_output=True, text=True)
    if mp4_result.returncode != 0:
        raise RuntimeError(f"Video dosyası indirilemedi: {mp4_result.stderr}")

    # Dosya Yolu Doğrulaması
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