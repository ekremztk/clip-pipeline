import os
import subprocess
import logging
import requests

logger = logging.getLogger(__name__)

# Railway üzerindeki Cobalt URL'niz
RAW_COBALT_URL = os.getenv("COBALT_API_URL", "cobalt-production-9619.up.railway.app")

if not RAW_COBALT_URL.startswith("http"):
    COBALT_API_URL = f"https://{RAW_COBALT_URL}"
else:
    COBALT_API_URL = RAW_COBALT_URL

def download_video(url: str, job_id: str):
    job_dir = f"output/{job_id}" # pipeline.py ile uyumlu klasör yapısı
    os.makedirs(job_dir, exist_ok=True)
    
    video_path = os.path.join(job_dir, "video.mp4")
    audio_path = os.path.join(job_dir, "audio.mp3")
    video_title = "YouTube Video"

    logger.info(f"[Downloader] 🚀 Cobalt API (Private) üzerinden indirme: {url}")
    
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ClipPipeline-Worker/1.0"
        }
        
        # Cobalt v11+ için en güvenli ve sade payload
        payload = {
            "url": url,
            "videoQuality": "1080"
        }
        
        # 1. API'den Link İste
        resp = requests.post(COBALT_API_URL, json=payload, headers=headers, timeout=30)
        
        if not resp.ok:
            logger.error(f"[Downloader] Cobalt API Hatası ({resp.status_code}): {resp.text}")
            resp.raise_for_status()

        data = resp.json()
        download_url = data.get("url")
        
        if not download_url:
            raise RuntimeError(f"Cobalt link dönmedi: {data}")

        # 2. Dosyayı İndir
        logger.info("[Downloader] 📥 Video dosyası çekiliyor...")
        with requests.get(download_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(video_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        # 3. Dosya Doğrulama (KRİTİK ADIM)
        file_size = os.path.getsize(video_path)
        logger.info(f"[Downloader] Dosya indirildi. Boyut: {file_size / (1024*1024):.2f} MB")
        
        if file_size < 1000: # 1KB'dan küçükse video olamaz, muhtemelen hata sayfasıdır
            with open(video_path, 'r', errors='ignore') as f:
                content = f.read(500)
            logger.error(f"[Downloader] Bozuk dosya içeriği: {content}")
            raise RuntimeError("İndirilen dosya geçerli bir video değil (çok küçük).")

    except Exception as e:
        logger.error(f"[Downloader] İndirme başarısız: {str(e)}")
        raise RuntimeError(f"Video indirilemedi: {e}")

    # 4. Sesi Çıkartma
    logger.info("[Downloader] 🎵 FFmpeg ile ses ayrıştırılıyor...")
    try:
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-q:a", "0",
            "-map", "a",
            audio_path
        ]
        # check=True hata durumunda exception fırlatır
        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
        logger.info("[Downloader] ✅ MP3 hazırlandı.")
    except subprocess.CalledProcessError as e:
        logger.error(f"[Downloader] FFmpeg Hatası: {e.stderr}")
        raise RuntimeError(f"FFmpeg ses ayrıştırma hatası: {e.stderr}")

    return video_path, audio_path, video_title