import os
import subprocess
import logging
import requests

logger = logging.getLogger(__name__)

# URL'ni çevresel değişkenden veya direkt kod içinden alıyoruz
RAW_COBALT_URL = os.getenv("COBALT_API_URL", "cobalt-production-9619.up.railway.app")

# KENDİ KENDİNİ İYİLEŞTİRME: Eğer URL'nin başında http/https yoksa otomatik olarak ekle!
if not RAW_COBALT_URL.startswith("http"):
    COBALT_API_URL = f"https://{RAW_COBALT_URL}"
else:
    COBALT_API_URL = RAW_COBALT_URL

def download_video(url: str, job_id: str):
    job_dir = f"jobs/{job_id}"
    os.makedirs(job_dir, exist_ok=True)
    
    video_path = os.path.join(job_dir, "video.mp4")
    audio_path = os.path.join(job_dir, "audio.mp3")
    video_title = "YouTube Video"

    logger.info(f"[Downloader] 🚀 SADECE Kendi Cobalt API'miz ile indirme başlatılıyor: {url}")
    logger.info(f"[Downloader] 🔗 API Adresi: {COBALT_API_URL}")
    
    try:
        # Kendi sunucumuz olduğu için maskeye gerek yok, sadece temel API kuralları yeterli.
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ClipPipeline-Worker/1.0"
        }
        
        payload = {
            "url": url,
        }
        
        # API'ye İstek At
        resp = requests.post(COBALT_API_URL, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        download_url = data.get("url")
        if not download_url:
            raise RuntimeError(f"Cobalt API indirme linki vermedi. Yanıt: {data}")
            
        logger.info("[Downloader] 📥 Kendi API'miz indirme linkini buldu! MP4 sunucumuza çekiliyor...")
        
        # Linkten videoyu sunucumuza (Railway) indir
        with requests.get(download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(video_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
        logger.info("[Downloader] ✅ Özel Cobalt API ile HD video başarıyla indirildi.")

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"[Downloader] ❌ API HTTP Hatası: {http_err.response.text}")
        raise RuntimeError(f"Video indirilemedi. API Hatası: {http_err.response.status_code}") from http_err
    except Exception as e:
        logger.error(f"[Downloader] ❌ İndirme sırasında beklenmeyen hata: {e}")
        raise RuntimeError("Video indirilemedi. Bağlantı kurulamadı.") from e

    # --- Sesi Çıkartma ---
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