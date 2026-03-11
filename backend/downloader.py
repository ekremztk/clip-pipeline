import os
import subprocess
import logging
import yt_dlp
import re

logger = logging.getLogger(__name__)

def extract_video_id(url: str):
    match = re.search(r"(?:v=|\/|youtu\.be\/|shorts\/)([0-9A-Za-z_-]{11})", url)
    if match:
        return match.group(1)
    raise ValueError("Geçersiz YouTube URL'si")

def download_video(url: str, job_id: str):
    job_dir = f"output/{job_id}" 
    os.makedirs(job_dir, exist_ok=True)
    
    video_path = os.path.join(job_dir, "video.mp4")
    audio_path = os.path.join(job_dir, "audio.mp3")
    
    # Bright Data Proxy Bilgilerin (Curl komutundan türetildi)
    proxy_user = "brd-customer-hl_f27914bd-zone-youtube_downloader"
    proxy_pass = "04cfjdel6c13"
    proxy_host = "brd.superproxy.io"
    proxy_port = "33335"
    
    # Proxy URL formatı: http://user:pass@host:port
    BRD_PROXY = f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"

    logger.info(f"[Downloader] 🚀 Bright Data Proxy (Residential) Devreye Alındı. Job: {job_id}")

    # yt-dlp Ayarları
    ydl_opts = {
        'proxy': BRD_PROXY,
        # En iyi mp4 formatını seç (video ve ses bir arada)
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': video_path,
        'quiet': False,
        'no_warnings': False,
        # YouTube'un bot korumasını aşmak için ek istemci kimlikleri
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'],
                'skip': ['dash', 'hls']
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"[Downloader] 📥 Video indiriliyor: {url}")
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'YouTube Video')

        logger.info(f"✅ Video başarıyla indirildi: {video_path}")

        # 2. Sesi Çıkartma (Mevcut FFmpeg mantığını koruyoruz)
        logger.info("[Downloader] 🎵 FFmpeg ile MP3 ayrıştırılıyor...")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-q:a", "0",
            "-map", "a",
            audio_path
        ]
        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
        logger.info("[Downloader] ✅ MP3 hazırlandı.")

        return video_path, audio_path, video_title

    except Exception as e:
        logger.error(f"[Downloader] Kritik Hata: {str(e)}")
        raise RuntimeError(f"Video indirme veya işleme başarısız oldu: {e}")