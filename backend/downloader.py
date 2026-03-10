import os
import subprocess
import logging
import requests

logger = logging.getLogger(__name__)

def download_video(url: str, job_id: str):
    """
    Çift Katmanlı (Bypass + Fallback) İndirme Mimarisini kullanarak
    YouTube videolarını güvenli bir şekilde indirir.
    """
    # 1. Klasör hazırlığı
    # Mevcut pipeline yapını bozmamak için job_id üzerinden ilerliyoruz
    job_dir = f"jobs/{job_id}"
    os.makedirs(job_dir, exist_ok=True)
    
    video_path = os.path.join(job_dir, "video.mp4")
    audio_path = os.path.join(job_dir, "audio.mp3")
    
    video_title = "YouTube Video" # Fallback varsayılan başlık

    # --- KATMAN A: Optimize Edilmiş yt-dlp (Mobil Bypass) ---
    logger.info(f"[Downloader] 🚀 Katman A (Mobil Cihaz Bypass) deneniyor: {url}")
    try:
        # Önce başlığı almayı deneyelim
        title_cmd =["yt-dlp", "--get-title", "--extractor-args", "youtube:player_client=android", url]
        title_result = subprocess.run(title_cmd, capture_output=True, text=True)
        if title_result.returncode == 0 and title_result.stdout.strip():
            video_title = title_result.stdout.strip()

        # Ana indirme komutu - Bot engeline karşı Android İstemcisi taklidi
        download_cmd =[
            "yt-dlp",
            "--rm-cache-dir", # Eski engellenmiş önbellekleri temizler
            "--extractor-args", "youtube:player_client=android,ios,web", # Bypass argümanı
            "--user-agent", "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.79 Mobile Safari/537.36",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "-o", video_path,
            url
        ]
        
        result = subprocess.run(download_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp red yedi: {result.stderr}")
            
        logger.info("[Downloader] ✅ Katman A ile indirme başarılı.")

    except Exception as e:
        logger.warning(f"[Downloader] ⚠️ Katman A başarısız oldu. Hata: {e}")
        logger.info("[Downloader] 🔄 Katman B (Fallback API) devreye giriyor! Sistem kurtarılıyor...")
        
        # --- KATMAN B: Fallback (Cobalt API) ---
        try:
            # Alternatif açık kaynak API'den direkt indirme linki istiyoruz
            api_url = "https://api.cobalt.tools/api/json"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "ClipPipeline-Worker/1.0"
            }
            payload = {
                "url": url,
                "vCodec": "h264",
                "vQuality": "1080",
                "isAudioOnly": False
            }
            
            resp = requests.post(api_url, json=payload, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") in ["redirect", "stream", "success"]:
                download_url = data.get("url")
                logger.info("[Downloader] 📥 Fallback API'den taze link alındı, dosya aktarılıyor...")
                
                with requests.get(download_url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(video_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                logger.info("[Downloader] ✅ Katman B (Fallback) ile indirme başarılı.")
            else:
                raise RuntimeError("Fallback API link üretemedi.")
                
        except Exception as fallback_e:
            logger.error(f"[Downloader] ❌ Tüm indirme yöntemleri (A ve B) başarısız oldu! Hata: {fallback_e}")
            raise RuntimeError("Video indirilemedi. YouTube çok sert bir kısıtlama uyguluyor olabilir.") from fallback_e

    # 3. Sesi Çıkartma (Whisper Transkripti İçin)
    logger.info("[Downloader] 🎵 Groq Whisper API için MP3 ayrıştırılıyor...")
    try:
        # İndirme işlemi A veya B hangi yöntemle yapılmış olursa olsun FFmpeg bunu dönüştürecektir
        ffmpeg_cmd =[
            "ffmpeg", "-i", video_path, 
            "-q:a", "0", "-map", "a", 
            audio_path, "-y" # -y dosya varsa üzerine yazar
        ]
        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
        logger.info("[Downloader] ✅ MP3 ayrıştırma başarılı.")
    except subprocess.CalledProcessError as e:
        logger.error(f"[Downloader] ❌ FFmpeg MP3 dönüştürme hatası: {e.stderr}")
        raise RuntimeError(f"Ses ayrıştırılamadı: {e.stderr}")

    return video_path, audio_path, video_title