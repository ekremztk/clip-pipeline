import os
import subprocess
import json
import time
from pathlib import Path

# --- SELF-HEALING (KENDİ KENDİNİ İYİLEŞTİRME) MEKANİZMASI ---
_YTDLP_UPDATED = False

def _ensure_ytdlp_updated():
    global _YTDLP_UPDATED
    if not _YTDLP_UPDATED:
        print("[Downloader] 🛠️ Self-Healing: yt-dlp sürümü kontrol ediliyor ve güncelleniyor...")
        subprocess.run(["pip", "install", "--upgrade", "yt-dlp"], capture_output=True)
        _YTDLP_UPDATED = True
        print("[Downloader] 🛠️ Self-Healing: yt-dlp güncel!")

def download_video(url: str, job_id: str) -> tuple[str, str, str]:
    _ensure_ytdlp_updated()

    job_dir = Path("output") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = Path("cookies.txt")
    has_cookies = cookie_path.exists() and cookie_path.stat().st_size > 0

    print(f"[Downloader] {job_id} için video bilgileri alınmaya çalışılıyor...")

    # ── MİMARİ GÜNCELLEME: ÇEREZLİ VE ÇEREZSİZ (ANONİM) İZOLASYON ──
    strategies =[
        {
            "name": "Strateji 1: Çerezli + Karma İstemci (android,ios,web)",
            "bypass_args": ["--extractor-args", "youtube:player_client=android,ios,web"],
            "use_cookies": True
        },
        {
            "name": "Strateji 2: Çerezli + TV İstemcisi",
            "bypass_args":["--extractor-args", "youtube:player_client=tv"],
            "use_cookies": True
        },
        {
            "name": "Strateji 3: ÇEREZSİZ (Anonim) + Mobil İstemci + Cache Temizliği",
            "bypass_args":["--extractor-args", "youtube:player_client=ios,android", "--rm-cache-dir"],
            "use_cookies": False
        },
        {
            "name": "Strateji 4: ÇEREZSİZ (Anonim) + Saf İstemci + Cache Temizliği",
            "bypass_args": ["--rm-cache-dir"],
            "use_cookies": False
        }
    ]

    info = None
    video_title = "Bilinmeyen Video"
    success_strategy = None

    # Adım 1: Sadece JSON Bilgisi Çek
    for attempt, strat in enumerate(strategies, 1):
        print(f"[Downloader] 🔄 Deneme {attempt}/4 - {strat['name']}")
        
        cmd_args = ["yt-dlp", "--no-warnings", "--dump-json"]
        
        # Eğer bu strateji cookie kullanıyorsa ekle, kullanmıyorsa zehirli cookie'yi at!
        if strat["use_cookies"] and has_cookies:
            cmd_args.extend(["--cookies", str(cookie_path)])
            
        cmd_args.extend(strat["bypass_args"])
        cmd_args.append(url)
        
        info_result = subprocess.run(cmd_args, capture_output=True, text=True)
        
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
        raise RuntimeError(f"Video bilgileri hiçbir stratejiyle alınamadı. Son hata: {info_result.stderr.strip()}")

    print(f"[Downloader] 📥 Video indiriliyor (Kazanan: {success_strategy['name']})...")
    
    # Adım 2: Kazanılan Strateji ile İndirme
    mp4_cmd =[
        "yt-dlp", "--no-warnings",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(job_dir / "source.%(ext)s")
    ]
    
    # İndirme aşamasında da sadece strateji cookie izin veriyorsa ekle
    if success_strategy["use_cookies"] and has_cookies:
        mp4_cmd.extend(["--cookies", str(cookie_path)])
        
    mp4_cmd.extend(success_strategy["bypass_args"])
    mp4_cmd.append(url)

    mp4_result = subprocess.run(mp4_cmd, capture_output=True, text=True)
    if mp4_result.returncode != 0:
        raise RuntimeError(f"Video dosyası indirilemedi: {mp4_result.stderr}")

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