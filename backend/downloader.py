import os
import subprocess
import json
from pathlib import Path

def download_video(url: str, job_id: str) -> tuple[str, str, str]:
    job_dir = Path("output") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    print("[Downloader] Video bilgileri alınıyor...")
    
    # 1. Bot Korumasını Aşmak İçin İstemci Taklidi (Bypass Args)
    # YouTube'a "Ben bir sunucu değilim, bir Android/iOS cihazıyım" diyoruz.
    bypass_args = [
        "--extractor-args", "youtube:player_client=android,ios,web"
    ]

    # 2. Çerez (Cookie) Dosyasını Kontrol Et
    cookie_args = []
    cookie_path = Path("cookies.txt")
    if cookie_path.exists() and cookie_path.stat().st_size > 0:
        cookie_args = ["--cookies", str(cookie_path)]
        print("[Downloader] 🍪 cookies.txt bulundu, yetkilendirme kullanılıyor.")
    else:
        print("[Downloader] ⚠️ Uyarı: cookies.txt bulunamadı veya boş. Bot engeline takılma riski yüksek!")

    # Bilgileri Çek
    info_cmd = ["yt-dlp", "--no-warnings", "--dump-json"] + cookie_args + bypass_args + [url]
    
    info_result = subprocess.run(info_cmd, capture_output=True, text=True)
    if info_result.returncode != 0:
        raise RuntimeError(f"Video bilgisi alınamadı (Bot Engeli Olabilir): {info_result.stderr}")
        
    info = json.loads(info_result.stdout)
    video_title = info.get("title", "Bilinmeyen Video")
    
    print(f"[Downloader] Başlık: {video_title}")
    print("[Downloader] Video indiriliyor...")
    
    # Videoyu İndir
    mp4_cmd = [
        "yt-dlp", "--no-warnings",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(job_dir / "source.%(ext)s")
    ] + cookie_args + bypass_args + [url]

    mp4_result = subprocess.run(mp4_cmd, capture_output=True, text=True)
    if mp4_result.returncode != 0:
        raise RuntimeError(f"Video indirilemedi: {mp4_result.stderr}")

    # Dosya Yolu Doğrulaması
    mp4_path = str(job_dir / "source.mp4")
    if not os.path.exists(mp4_path):
        files = list(job_dir.glob("source.*"))
        if files:
            mp4_path = str(files[0])

    print("[Downloader] Ses çıkarılıyor...")
    mp3_path = str(job_dir / "audio.mp3")
    mp3_cmd = [
        "ffmpeg", "-y", "-i", mp4_path,
        "-q:a", "0", "-map", "a",
        mp3_path
    ]
    
    mp3_result = subprocess.run(mp3_cmd, capture_output=True, text=True)
    if mp3_result.returncode != 0:
         raise RuntimeError(f"Ses çıkarılamadı: {mp3_result.stderr}")

    print(f"[Downloader] ✅ Tamamlandı: {video_title}")
    return mp4_path, mp3_path, video_title