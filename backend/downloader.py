import os
import subprocess
import logging
from pytubefix import YouTube

logger = logging.getLogger(__name__)

def download_video(url: str, job_id: str):
    job_dir = f"output/{job_id}" 
    os.makedirs(job_dir, exist_ok=True)
    
    video_path = os.path.join(job_dir, "video.mp4")
    audio_path = os.path.join(job_dir, "audio.mp3")
    
    logger.info(f"[Downloader] 🚀 Pytubefix (PO_Token Mimarisi) ile indirme başlıyor: {url}")
    
    try:
        # use_po_token=True: YouTube'un son bot korumasını (403 hatalarını) aşar
        # client='WEB': Masaüstü tarayıcı gibi davranır
        yt = YouTube(url, client='WEB', use_po_token=True)
        video_title = yt.title
        logger.info(f"[Downloader] Video bulundu: {video_title}")

        # Progressive (Ses ve Görüntü birleşik) en yüksek çözünürlüğü seçer. 
        # (Shorts/Reels için ideal ve Railway CPU'su için en hafif yöntemdir)
        stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
        
        if not stream:
            raise RuntimeError("Uygun MP4 video akışı bulunamadı!")

        logger.info(f"[Downloader] 📥 Video indiriliyor (Çözünürlük: {stream.resolution})...")
        
        # Dosyayı indir
        stream.download(output_path=job_dir, filename="video.mp4")
        
        # 3. Dosya Doğrulama
        file_size = os.path.getsize(video_path)
        logger.info(f"[Downloader] ✅ Video başarıyla indirildi. Boyut: {file_size / (1024*1024):.2f} MB")
        
        if file_size < 100000: # 100KB altıysa sahte veridir
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