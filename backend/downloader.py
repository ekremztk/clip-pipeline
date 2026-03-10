import os
import subprocess
import logging
import requests

logger = logging.getLogger(__name__)

def download_video(url: str, job_id: str):
    job_dir = f"jobs/{job_id}"
    os.makedirs(job_dir, exist_ok=True)
    
    video_path = os.path.join(job_dir, "video.mp4")
    audio_path = os.path.join(job_dir, "audio.mp3")
    video_title = "YouTube Video"

    # --- KATMAN A: iOS Bypass (DRM'siz, Yüksek Kalite, Bot Engeli Aşma) ---
    logger.info(f"[Downloader] 🚀 Katman A (iOS Bypass - DRM'siz YÜKSEK KALİTE) deneniyor: {url}")
    try:
        title_cmd =["yt-dlp", "--get-title", "--extractor-args", "youtube:player_client=ios", url]
        title_result = subprocess.run(title_cmd, capture_output=True, text=True)
        if title_result.returncode == 0 and title_result.stdout.strip():
            video_title = title_result.stdout.strip()

        # KALİTE GÜNCELLEMESİ: iOS İstemcisi ve Safari User-Agent
        download_cmd =[
            "yt-dlp",
            "--rm-cache-dir",
            "--extractor-args", "youtube:player_client=ios", # iOS: DRM içermez, yüksek kalite verir
            "--user-agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", video_path,
            url
        ]
        
        result = subprocess.run(download_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp red yedi: {result.stderr}")
            
        logger.info("[Downloader] ✅ Katman A ile YÜKSEK KALİTELİ indirme başarılı.")

    except Exception as e:
        logger.warning(f"[Downloader] ⚠️ Katman A başarısız oldu. Hata: {e}")
        logger.info("[Downloader] 🔄 Katman B (Cobalt API v7 Fallback) devreye giriyor! Sistem kurtarılıyor...")
        
        # --- KATMAN B: Fallback (Cobalt API v7 Güncel Sürüm) ---
        try:
            api_url = "https://api.cobalt.tools/"  # v7 ile uç nokta güncellendi (artık /api/json yok)
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "ClipPipeline-Worker/1.0"
            }
            payload = {
                "url": url,
                "videoQuality": "1080", # v7 parametre güncellemesi
                "filenamePattern": "classic"
            }
            
            resp = requests.post(api_url, json=payload, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            
            # v7 sürümü direkt olarak url döndürebilir veya status = success olabilir
            download_url = data.get("url")
            
            if download_url:
                logger.info("[Downloader] 📥 Fallback API'den taze HD link alındı, dosya aktarılıyor...")
                
                with requests.get(download_url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(video_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                logger.info("[Downloader] ✅ Katman B (Fallback) ile HD indirme başarılı.")
            else:
                raise RuntimeError("Fallback API v7 link üretemedi. Yanıt: " + str(data))
                
        except Exception as fallback_e:
            logger.error(f"[Downloader] ❌ Tüm indirme yöntemleri başarısız oldu! Hata: {fallback_e}")
            raise RuntimeError("Video indirilemedi. Bypass mekanizmaları aşılamadı.") from fallback_e

    # --- 3. Sesi Çıkartma (Whisper Transkripti İçin) ---
    logger.info("[Downloader] 🎵 Groq Whisper API için MP3 ayrıştırılıyor...")
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