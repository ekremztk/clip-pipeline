import os
import subprocess
import logging
import yt_dlp
import re
from pathlib import Path

logger = logging.getLogger(__name__)

def extract_video_id(url: str):
    match = re.search(r"(?:v=|\/|youtu\.be\/|shorts\/)([0-9A-Za-z_-]{11})", url)
    if match:
        return match.group(1)
    raise ValueError("Geçersiz YouTube URL'si")

def download_video(url: str, job_id: str):
    # Dizinleri hazırla
    job_dir = Path(f"output/{job_id}")
    job_dir.mkdir(parents=True, exist_ok=True)
    
    video_path = job_dir / "video.mp4"
    audio_path = job_dir / "audio.mp3"
    
    # Çerez dosyası kontrolü
    cookie_path = "cookies.txt"
    if not os.path.exists(cookie_path):
        logger.warning(f"⚠️ {cookie_path} bulunamadı! İndirme başarısız olabilir.")

    # yt-dlp Ayarları: Daha esnek ve hata toleranslı
    ydl_opts = {
        'cookiefile': cookie_path if os.path.exists(cookie_path) else None,
        # En iyi kaliteyi seç, mp4 bulamazsan herhangi bir formatı indir ve mp4'e çevir
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': str(job_dir / "video.%(ext)s"),
        'merge_output_format': 'mp4',
        'quiet': False,
        'no_warnings': False,
        # Çerezlerle çakışmaması için istemci kısıtlamalarını kaldırdık veya web ağırlıklı yaptık
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'mweb'], # Cookies ile en uyumlu istemciler
            }
        },
        # Hata anında indirmeyi durdurma, format hatası alırsan esneklik sağla
        'ignoreerrors': False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"[Downloader] İndirme başlatıldı: {url}")
            info = ydl.extract_info(url, download=True)
            
            # İndirilen dosyanın adını tam olarak bul (uzantı değişmiş olabilir)
            downloaded_file = ydl.prepare_filename(info)
            # Eğer uzantı mp4 değilse ffmpeg ile çevrilmiş halini kontrol et
            actual_video_path = downloaded_file.rsplit('.', 1)[0] + ".mp4"
            
            # Dosya adını video.mp4 olarak sabitle
            if os.path.exists(downloaded_file) and downloaded_file != str(video_path):
                os.rename(downloaded_file, str(video_path))
            
            video_title = info.get('title', 'YouTube Video')

        logger.info(f"✅ Video hazır: {video_path}")

        # 2. Sesi Çıkartma (FFmpeg ile MP3'e zorla)
        logger.info("[Downloader] 🎵 FFmpeg ile MP3 ayrıştırılıyor...")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn", # Sadece ses
            "-acodec", "libmp3lame",
            "-q:a", "2",
            str(audio_path)
        ]
        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
        logger.info("[Downloader] ✅ MP3 hazır.")

        return str(video_path), str(audio_path), video_title

    except Exception as e:
        logger.error(f"[Downloader] Kritik Hata: {str(e)}")
        # Eğer format hatası devam ederse, kullanıcıya daha anlamlı bir hata dön
        if "Requested format is not available" in str(e):
            raise RuntimeError("YouTube bu video için uygun format sağlamadı. Lütfen çerezlerinizi güncelleyin.")
        raise RuntimeError(f"Video indirme hatası: {e}")