import os
import logging
import yt_dlp

logger = logging.getLogger(__name__)

def download_video(url: str, job_id: str):
    job_dir = f"output/{job_id}" 
    os.makedirs(job_dir, exist_ok=True)
    video_path = os.path.join(job_dir, "video.mp4")
    
    # cookies.txt dosyasının yolu (main.py ile aynı dizindeyse direkt adı)
    cookie_path = "cookies.txt" 

    ydl_opts = {
        'cookiefile': cookie_path, # PROXY YERİNE COOKIE KULLANIYORUZ
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': video_path,
        'quiet': False,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'],
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"[Downloader] Çerezler kullanılarak indiriliyor: {url}")
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'YouTube Video')

        return video_path, video_path.replace(".mp4", ".mp3"), video_title # Basitleştirilmiş ses dönüşü
    except Exception as e:
        logger.error(f"[Downloader] Çerez yöntemiyle de hata alındı: {str(e)}")
        raise RuntimeError(f"İndirme başarısız: {e}")