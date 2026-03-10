import os
import subprocess
import logging
import requests

logger = logging.getLogger(__name__)

# KENDİ COBALT API URL'Nİ BURAYA YAZACAKSIN (Adım 2'de anlattım)
# Şimdilik halka açık sunucuyu (tarayıcı maskesiyle) kullanıyor.
COBALT_API_URL = os.getenv("COBALT_API_URL", "cobalt-production-9619.up.railway.app")

def download_video(url: str, job_id: str):
    job_dir = f"jobs/{job_id}"
    os.makedirs(job_dir, exist_ok=True)
    
    video_path = os.path.join(job_dir, "video.mp4")
    audio_path = os.path.join(job_dir, "audio.mp3")
    video_title = "YouTube Video"

    logger.info(f"[Downloader] 🚀 SADECE Cobalt API ile indirme başlatılıyor: {url}")
    
    try:
        # Public API'yi bot olmadığımıza ikna eden kusursuz maske
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Origin": "https://cobalt.tools",
            "Referer": "https://cobalt.tools/"
        }
        
        # Cobalt v7 API formatı
        payload = {
            "url": url,
            "videoQuality": "1080",
            "filenamePattern": "classic"
        }
        
        # API'ye İstek At
        resp = requests.post(COBALT_API_URL, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        # API bize indirme linki veriyor
        download_url = data.get("url")
        if not download_url:
            raise RuntimeError(f"Cobalt API indirme linki vermedi. Yanıt: {data}")
            
        logger.info("[Downloader] 📥 Cobalt API indirme linkini buldu (Bypass Başarılı!), MP4 çekiliyor...")
        
        # Linkten videoyu sunucumuza (Railway) indir
        with requests.get(download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(video_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
        logger.info("[Downloader] ✅ Cobalt API ile HD video başarıyla indirildi.")

    except Exception as e:
        logger.error(f"[Downloader] ❌ Cobalt API indirme hatası: {e}")
        raise RuntimeError("Video indirilemedi. Bağlantı reddedildi.") from e

    # --- Sesi Çıkartma (Aşama 1'in transkript modülünü bozmamak için) ---
    logger.info("[Downloader] 🎵 MP3 ayrıştırılıyor...")
    try:
        ffmpeg_cmd =[
            "ffmpeg", "-i", video_path, 
            "-q:a", "0", "-map", "a", 
            audio_path, "-y"
        ]
        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
        logger.info("[Downloader] ✅ MP3 ayrıştırma başarılı.")
    except subprocess.CalledProcessError as e:
        logger.error(f"[Downloader] ❌ FFmpeg MP3 dönüştürme hatası: {e.stderr}")
        raise RuntimeError(f"Ses ayrıştırılamadı: {e.stderr}")

    return video_path, audio_path, video_title