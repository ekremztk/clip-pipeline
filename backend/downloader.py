import os
import subprocess
import json
import time
from pathlib import Path

def download_video(url: str, job_id: str) -> tuple[str, str, str]:
    job_dir = Path("output") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = Path("cookies.txt")

    print(f"[Downloader] {job_id} için video bilgileri alınmaya çalışılıyor...")

    # ── HATA TOLERANSI: ORİJİNAL BYPASS + ALTERNATİFLER ──
    # Orijinal projedeki en iyi çalışan taktikleri (android,ios,web) 
    # fallback zinciriyle birleştirdik.
    strategies =[
        {
            "name": "Strateji 1: Orijinal Karma (android,ios,web)",
            "bypass_args":["--extractor-args", "youtube:player_client=android,ios,web"]
        },
        {
            "name": "Strateji 2: TV & Web Alternatifi",
            "bypass_args":["--extractor-args", "youtube:player_client=tv,web"]
        },
        {
            "name": "Strateji 3: Saf İstemci (Argümansız)",
            "bypass_args":[]
        }
    ]

    # Çerezleri ayarla
    cookie_args =[]
    if cookie_path.exists() and cookie_path.stat().st_size > 0:
        cookie_args = ["--cookies", str(cookie_path)]
        print("[Downloader] 🍪 cookies.txt bulundu, yetkilendirme kullanılıyor.")
    else:
        print("[Downloader] ⚠️ Uyarı: cookies.txt bulunamadı!")

    info = None
    video_title = "Bilinmeyen Video"
    success_strategy = None

    # Adım 1: Sadece JSON Bilgisi Çek (Format dayatması YOK!)
    for attempt, strat in enumerate(strategies, 1):
        print(f"[Downloader] 🔄 Deneme {attempt}/3 - {strat['name']}")
        
        # DİKKAT: Burada -f kullanmıyoruz. Sadece meta verilerini çekiyoruz.
        info_cmd =["yt-dlp", "--no-warnings", "--dump-json"] + cookie_args + strat["bypass_args"] + [url]
        
        info_result = subprocess.run(info_cmd, capture_output=True, text=True)
        
        if info_result.returncode == 0:
            try:
                info = json.loads(info_result.stdout)
                video_title = info.get("title", "Bilinmeyen Video")
                success_strategy = strat
                print(f"[Downloader] ✅ Bilgiler başarıyla çekildi. Başlık: {video_title}")
                break
            except json.JSONDecodeError:
                pass
        
        print(f"[Downloader] ⚠️ Deneme {attempt} başarısız: {info_result.stderr.strip()[:200]}...")
        time.sleep(2)

    if not success_strategy:
        raise RuntimeError(f"Video bilgileri alınamadı (Bot veya Format engeli). Son hata: {info_result.stderr.strip()}")

    print(f"[Downloader] 📥 Video indiriliyor (Kazanan: {success_strategy['name']})...")
    
    # Adım 2: Geniş Kapsamlı Formatla İndirme (Senin orijinal yaklaşımın)
    mp4_cmd =[
        "yt-dlp", "--no-warnings",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(job_dir / "source.%(ext)s")
    ] + cookie_args + success_strategy["bypass_args"] + [url]

    mp4_result = subprocess.run(mp4_cmd, capture_output=True, text=True)
    if mp4_result.returncode != 0:
        raise RuntimeError(f"Video dosyası indirilemedi: {mp4_result.stderr}")

    # Dosya Yolu Doğrulaması
    mp4_path = str(job_dir / "source.mp4")
    if not os.path.exists(mp4_path):
        files = list(job_dir.glob("source.*"))
        if files:
            mp4_path = str(files[0])

    print("[Downloader] 🎵 Ses dosyası (MP3) ayrıştırılıyor...")
    mp3_path = str(job_dir / "audio.mp3")
    mp3_cmd =[
        "ffmpeg", "-y", "-i", mp4_path,
        "-q:a", "0", "-map", "a",
        mp3_path
    ]
    
    mp3_result = subprocess.run(mp3_cmd, capture_output=True, text=True)
    if mp3_result.returncode != 0:
         raise RuntimeError(f"Ses ayrıştırılamadı: {mp3_result.stderr}")

    print(f"[Downloader] 🎉 İndirme ve ayrıştırma tamamlandı: {video_title}")
    return mp4_path, mp3_path, video_title