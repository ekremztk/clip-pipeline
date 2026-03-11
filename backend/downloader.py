import os
import subprocess
import logging
import requests
import re

logger = logging.getLogger(__name__)

# Piped API Public Instances (Hata toleransı için 4 farklı yedekli sunucu)
PIPED_INSTANCES =[
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.tokhmi.xyz",
    "https://pipedapi.adminforge.de",
    "https://api.piped.projectsegfau.lt"
]

def extract_video_id(url: str):
    # Her türlü YouTube URL'sinden (Shorts, youtu.be, watch?v=) 11 haneli ID'yi çıkartır
    match = re.search(r"(?:v=|\/|youtu\.be\/|shorts\/)([0-9A-Za-z_-]{11})", url)
    if match:
        return match.group(1)
    raise ValueError("Geçersiz YouTube URL'si")

def download_video(url: str, job_id: str):
    job_dir = f"output/{job_id}" 
    os.makedirs(job_dir, exist_ok=True)
    
    video_path = os.path.join(job_dir, "video.mp4")
    audio_path = os.path.join(job_dir, "audio.mp3")
    
    video_id = extract_video_id(url)
    logger.info(f"[Downloader] 👻 Hayalet Mimarisi (Piped Proxy) Başlatıldı. Video ID: {video_id}")

    stream_data = None
    
    # 1. API'den Akış Verilerini Al (Fallback Sistemli)
    for api_url in PIPED_INSTANCES:
        try:
            logger.info(f"[Downloader] 🔄 Tünel deneniyor: {api_url}")
            resp = requests.get(f"{api_url}/streams/{video_id}", timeout=15)
            if resp.status_code == 200:
                stream_data = resp.json()
                logger.info("[Downloader] ✅ Tünel bağlantısı başarılı!")
                break
        except Exception as e:
            logger.warning(f"[Downloader] ⚠️ Tünel yanıt vermedi ({api_url}). Diğerine geçiliyor...")
            continue

    if not stream_data:
        raise RuntimeError("Hiçbir Piped Proxy sunucusu yanıt vermedi. Sistemler geçici olarak yoğun olabilir.")

    video_title = stream_data.get("title", "YouTube Video")
    
    # 2. Uygun MP4 Akışını Seç (Progressive: Ses ve Görüntü bir arada)
    video_streams = stream_data.get("videoStreams", [])
    progressive_streams =[s for s in video_streams if s.get("videoOnly") == False and s.get("mimeType") == "video/mp4"]
    
    if progressive_streams:
        best_stream = sorted(progressive_streams, key=lambda x: x.get("bitrate", 0), reverse=True)[0]
        download_url = best_stream.get("url")
    else:
        logger.warning("[Downloader] Uyarı: Birleşik akış bulunamadı, sessiz ana video çekiliyor...")
        download_url = video_streams[0].get("url") if video_streams else None

    if not download_url:
        raise RuntimeError("Piped API üzerinden indirilebilir video akışı bulunamadı.")

    # 3. Proxy Üzerinden İndirme (Google Railway'i Görmez)
    logger.info(f"[Downloader] 📥 Video indiriliyor (Proxy tünelinden)...")
    try:
        with requests.get(download_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(video_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        file_size = os.path.getsize(video_path)
        logger.info(f"[Downloader] ✅ Video indirildi. Boyut: {file_size / (1024*1024):.2f} MB")
        
        if file_size < 100000:
            raise RuntimeError(f"İndirilen dosya çok küçük. Bot koruması proxy'yi de kesmiş olabilir: {file_size} bytes")

    except Exception as e:
        logger.error(f"[Downloader] İndirme başarısız: {str(e)}")
        raise RuntimeError(f"Video indirilemedi: {e}")

    # 4. Sesi Çıkartma
    logger.info("[Downloader] 🎵 FFmpeg ile MP3 ayrıştırılıyor...")
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