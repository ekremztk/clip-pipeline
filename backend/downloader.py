import os
import subprocess
import logging
import requests

logger = logging.getLogger(__name__)

# Kendi banlı Railway sunucumuz yerine Resmi/Public Cobalt API kullanıyoruz
COBALT_API_URL = "https://api.cobalt.tools"

def download_video(url: str, job_id: str):
    job_dir = f"output/{job_id}" 
    os.makedirs(job_dir, exist_ok=True)
    
    video_path = os.path.join(job_dir, "video.mp4")
    audio_path = os.path.join(job_dir, "audio.mp3")
    video_title = "YouTube Video"

    logger.info(f"[Downloader] 🚀 Resmi Cobalt API (Public) üzerinden indirme: {url}")
    
    try:
        # Resmi sunucunun bizi bot sanmaması için gerçekçi tarayıcı başlıkları (Headers)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Origin": "https://cobalt.tools",
            "Referer": "https://cobalt.tools/"
        }
        
        payload = {
            "url": url,
            "videoQuality": "1080"
        }
        
        # 1. API'den Link İste
        logger.info("[Downloader] ⏳ Cobalt API'den proxy linki bekleniyor...")
        resp = requests.post(COBALT_API_URL, json=payload, headers=headers, timeout=30)
        
        if not resp.ok:
            logger.error(f"[Downloader] Public Cobalt API Hatası ({resp.status_code}): {resp.text}")
            resp.raise_for_status()

        data = resp.json()
        download_url = data.get("url")
        
        if not download_url:
            raise RuntimeError(f"Cobalt public sunucusu link dönmedi: {data}")

        # 2. Dosyayı İndir
        logger.info(f"[Downloader] 📥 İndirme Linki Alındı (Public Proxy): {download_url.split('?')[0]}...")
        
        download_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "*/*"
        }

        with requests.get(download_url, stream=True, timeout=120, headers=download_headers) as r:
            r.raise_for_status()
            with open(video_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        # 3. Dosya Doğrulama
        file_size = os.path.getsize(video_path)
        logger.info(f"[Downloader] ✅ Dosya indirildi. Boyut: {file_size / (1024*1024):.2f} MB")
        
        if file_size < 100000: # 100KB altıysa sahte veridir (0 bytes vb.)
            raise RuntimeError(f"İndirilen dosya geçerli bir video değil. Boyut: {file_size} bytes")

    except Exception as e:
        logger.error(f"[Downloader] İndirme başarısız: {str(e)}")
        raise RuntimeError(f"Video indirilemedi: {e}")

    # 4. Sesi Çıkartma
    logger.info("[Downloader] 🎵 FFmpeg ile ses ayrıştırılıyor...")
    try:
        ffmpeg_cmd =[
            "ffmpeg", "-y",
            "-i", video_path,
            "-q:a", "0",
            "-map", "a",
            audio_path
        ]
        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
        logger.info("[Downloader] ✅ MP3 hazırlandı.")
    except subprocess.CalledProcessError as e:
        logger.error(f"[Downloader] FFmpeg Hatası: {e.stderr}")
        raise RuntimeError(f"FFmpeg ses ayrıştırma hatası: {e.stderr}")

    return video_path, audio_path, video_title