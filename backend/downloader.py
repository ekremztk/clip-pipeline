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
    
    # Çerez dosyası kontrolü (OAuth2 varken ikinci planda kalır ama yedek iyidir)
    cookie_path = "cookies.txt"

    # yt-dlp Ayarları: OAuth2 ve TV İstemcisi Odaklı
    ydl_opts = {
        # --- OAuth2 Yapılandırması ---
        'username': 'oauth2',
        'password': '', # Boş bırakılır, etkileşimli giriş yapılır
        
        'cookiefile': cookie_path if os.path.exists(cookie_path) else None,
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': str(job_dir / "video.%(ext)s"),
        'merge_output_format': 'mp4',
        'quiet': False,
        'no_warnings': False,
        
        'extractor_args': {
            'youtube': {
                # OAuth2 için en stabil istemciler TV ve TVHTML5'tir
                'player_client': ['tv', 'tvhtml5', 'android', 'web'],
                'skip': ['dash', 'hls']
            }
        },
        'nocheckcertificate': True,
        'ignoreerrors': False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"[Downloader] 📺 OAuth2 (Cihaz Girişi) ile indirme başlatıldı: {url}")
            
            # extract_info aşamasında eğer ilk giriş ise terminale/loglara kod basacaktır
            info = ydl.extract_info(url, download=True)
            
            downloaded_file = ydl.prepare_filename(info)
            
            # Uzantı ne olursa olsun video.mp4'e sabitle
            if os.path.exists(downloaded_file) and downloaded_file != str(video_path):
                # Eğer indirilen dosya mp4 değilse ffmpeg ile convert et
                if not downloaded_file.endswith(".mp4"):
                    logger.info(f"[Downloader] 🔄 Format dönüştürülüyor ({downloaded_file} -> mp4)")
                    subprocess.run(["ffmpeg", "-y", "-i", downloaded_file, str(video_path)], check=True)
                    os.remove(downloaded_file)
                else:
                    os.rename(downloaded_file, str(video_path))
            
            video_title = info.get('title', 'YouTube Video')

        logger.info(f"✅ Video hazır: {video_path}")

        # 2. Sesi Çıkartma
        logger.info("[Downloader] 🎵 FFmpeg ile MP3 ayrıştırılıyor...")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "libmp3lame",
            "-q:a", "2",
            str(audio_path)
        ]
        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
        logger.info("[Downloader] ✅ MP3 hazır.")

        return str(video_path), str(audio_path), video_title

    except Exception as e:
        logger.error(f"[Downloader] Kritik Hata: {str(e)}")
        raise RuntimeError(f"Video indirme hatası (OAuth2): {e}")