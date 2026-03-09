import subprocess
import re
from pathlib import Path

OUTPUT_DIR = Path("output")

def sanitize(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:60]

def download_video(url: str, job_id: str) -> tuple[str, str, str]:
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    mp4_path = str(job_dir / "source.mp4")
    mp3_path = str(job_dir / "audio.mp3")

    # ── Get title ─────────────────────────────────────────
    info_cmd = ["yt-dlp", "--no-warnings", "--cookies", "cookies.txt", "--print", "title", "--no-download", url]
    result = subprocess.run(info_cmd, capture_output=True, text=True)
    title = sanitize(result.stdout.strip()) if result.returncode == 0 else "video"
    print(f"[Downloader] Başlık: {title}")

    # ── Download video ────────────────────────────────────
    print("[Downloader] Video indiriliyor...")
    mp4_cmd = [
        "yt-dlp", "--no-warnings", "--cookies", "cookies.txt",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(job_dir / "source.%(ext)s"),
        url,
    ]
    result = subprocess.run(mp4_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Video indirilemedi: {result.stderr}")

    # ── Ses FFmpeg ile çıkar ──────────────────────────────
    print("[Downloader] Ses çıkarılıyor...")
    mp3_cmd = [
        "ffmpeg", "-y", "-i", mp4_path,
        "-vn", "-acodec", "libmp3lame", "-q:a", "2",
        mp3_path
    ]
    result = subprocess.run(mp3_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Ses çıkarılamadı: {result.stderr}")

    print(f"[Downloader] ✅ Tamamlandı: {title}")
    return mp4_path, mp3_path, title