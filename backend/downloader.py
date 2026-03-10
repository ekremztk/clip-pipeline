import os
import subprocess
import time
from pathlib import Path

# --- KENDİ KENDİNİ GÜNCELLEME (Yt-dlp'yi YouTube'un bot güncellemelerine karşı diri tutar) ---
_YTDLP_UPDATED = False
def _ensure_ytdlp_updated():
    global _YTDLP_UPDATED
    if not _YTDLP_UPDATED:
        print("[Downloader] 🛠️ yt-dlp güncelleniyor (Bypass için hayati önem taşır)...")
        subprocess.run(["pip", "install", "--upgrade", "yt-dlp"], capture_output=True)
        _YTDLP_UPDATED = True

def download_video(url: str, job_id: str) -> tuple[str, str, str]:
    _ensure_ytdlp_updated()

    job_dir = Path("output") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = Path("cookies.txt")

    print(f"[Downloader] {job_id} işlemi başlıyor. Temiz ve aşamasız indirme...")

    # SENİN ORİJİNAL BYPASS TAKTİĞİN + ÖNBELLEK TEMİZLİĞİ (Eski PO tokenları silmek için)
    bypass_args =["--extractor-args", "youtube:player_client=android,ios,web", "--rm-cache-dir"]

    cookie_args =[]
    if cookie_path.exists() and cookie_path.stat().st_size > 0:
        cookie_args = ["--cookies", str(cookie_path)]
        print("[Downloader] 🍪 Cookie bulundu (Ban riskine karşı kontrollü kullanılacak).")

    # ── 1. AŞAMA: SADECE BAŞLIĞI ÇEK (Format Hatası Almamak İçin dump-json Kullanmıyoruz) ──
    print("[Downloader] Video bilgisi alınıyor...")
    title_cmd =["yt-dlp", "--no-warnings", "--print", "%(title)s"] + cookie_args + bypass_args + [url]
    title_result = subprocess.run(title_cmd, capture_output=True, text=True)
    
    video_title = title_result.stdout.strip()
    if not video_title or title_result.returncode != 0:
        print(f"[Downloader] ⚠️ Başlık alınamadı (Fallback kullanılıyor). Hata detayı: {title_result.stderr.strip()}")
        video_title = "YouTube Video"

    print(f"[Downloader] ✅ Başlık: {video_title}")
    print("[Downloader] 📥 Video indiriliyor...")

    # ── 2. AŞAMA: SENİN ESNEK FORMAT MANTIĞINLA İNDİRME ──
    mp4_cmd =[
        "yt-dlp", "--no-warnings",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(job_dir / "source.%(ext)s")
    ] + cookie_args + bypass_args + [url]

    mp4_result = subprocess.run(mp4_cmd, capture_output=True, text=True)
    
    # EĞER ÇÖKERSE VE SEBEBİ COOKIE İSE, COOKIESİZ (ANONİM) ZORLA!
    if mp4_result.returncode != 0:
        if "Sign in to confirm you’re not a bot" in mp4_result.stderr and cookie_args:
            print("[Downloader] 🚨 Cookie zehirlenmiş (Bot Flag)! Cookie'siz, tertemiz bir anonim istek atılıyor...")
            
            # Komuttan cookie argümanlarını çıkar
            mp4_cmd_nocook =[cmd for cmd in mp4_cmd if cmd not in ["--cookies", str(cookie_path)]]
            mp4_result = subprocess.run(mp4_cmd_nocook, capture_output=True, text=True)
            
            if mp4_result.returncode != 0:
                raise RuntimeError(f"Cookie'siz anonim deneme de başarısız oldu: {mp4_result.stderr}")
        else:
            raise RuntimeError(f"Video dosyası indirilemedi: {mp4_result.stderr}")

    mp4_path = str(job_dir / "source.mp4")
    if not os.path.exists(mp4_path):
        files = list(job_dir.glob("source.*"))
        if files:
            mp4_path = str(files[0])

    print("[Downloader] 🎵 Ses dosyası ayrıştırılıyor...")
    mp3_path = str(job_dir / "audio.mp3")
    mp3_cmd =[
        "ffmpeg", "-y", "-i", mp4_path,
        "-q:a", "0", "-map", "a",
        mp3_path
    ]
    
    mp3_result = subprocess.run(mp3_cmd, capture_output=True, text=True)
    if mp3_result.returncode != 0:
         raise RuntimeError(f"Ses ayrıştırılamadı: {mp3_result.stderr}")

    print(f"[Downloader] 🎉 İşlem tamamlandı: {video_title}")
    return mp4_path, mp3_path, video_title