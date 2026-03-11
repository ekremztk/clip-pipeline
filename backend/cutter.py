"""
cutter.py
---------
FFmpeg ile video kesme.
PySceneDetect ile en yakın doğal sahne geçişine snap yapar.
Dosya adına _start_XXX ekler (subtitler.py için).
Mac işlemcisine (threads 0 & ultrafast) optimize edilmiştir.
"""

import subprocess
import json
from pathlib import Path

PADDING = 1.5        # saniye — başa ve sona eklenir
MAX_TOTAL = 61       # PADDING dahil maksimum
MIN_TOTAL = 5        # Minimum klip süresi

try:
    from scenedetect import VideoManager, SceneManager
    from scenedetect.detectors import ContentDetector
    SCENEDETECT_AVAILABLE = True
except ImportError:
    SCENEDETECT_AVAILABLE = False
    print("[Cutter] ⚠️ PySceneDetect kurulu değil. pip install scenedetect[opencv]")


def get_video_duration(mp4_path: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", mp4_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return float(json.loads(result.stdout)["format"]["duration"])
    return 9999.0


def get_scene_cuts(mp4_path: str) -> list[float]:
    """PySceneDetect ile doğal sahne geçişlerini tespit eder."""
    if not SCENEDETECT_AVAILABLE:
        return []

    try:
        video_manager = VideoManager([mp4_path])
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=30.0))

        video_manager.set_downscale_factor()
        video_manager.start()
        scene_manager.detect_scenes(frame_source=video_manager)
        scene_list = scene_manager.get_scene_list()
        video_manager.release()

        # Her sahnenin başlangıç zamanını saniye olarak al
        cuts = [scene[0].get_seconds() for scene in scene_list]
        print(f"[Cutter] {len(cuts)} sahne geçişi tespit edildi.")
        return cuts
    except Exception as e:
        print(f"[Cutter] PySceneDetect hatası: {e}")
        return []


def snap_to_scene(target_sec: float, scene_cuts: list[float], window: float = 2.5) -> float:
    """
    Hedef saniyeye en yakın sahne geçişine snap yapar.
    Pencere dışında sahne yoksa orijinal değeri döndürür.
    """
    if not scene_cuts:
        return target_sec

    best = target_sec
    best_dist = float("inf")

    for cut in scene_cuts:
        dist = abs(cut - target_sec)
        if dist <= window and dist < best_dist:
            best_dist = dist
            best = cut

    if best != target_sec:
        print(f"[Cutter] Snap: {target_sec:.1f}s → {best:.1f}s (sahne geçişi)")

    return best


def cut_clips(mp4_path: str, clips_data: list[dict], job_id: str) -> list[str]:
    job_dir = Path("output") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    clip_paths = []
    video_duration = get_video_duration(mp4_path)

    # Sahne geçişlerini önceden al
    print("[Cutter] Sahne geçişleri tespit ediliyor...")
    scene_cuts = get_scene_cuts(mp4_path)

    for i, clip in enumerate(clips_data):
        # Gemini promptundan gelen yeni JSON anahtarlarını okuyoruz (start_time, end_time)
        try:
            raw_start = float(clip.get("start_time", 0))
            raw_end = float(clip.get("end_time", 30))
            hook_text = clip.get("hook_text", "klip")
        except (ValueError, TypeError):
            raw_start, raw_end = 0.0, 30.0
            hook_text = "klip"

        # Mantıksız değer kontrolü
        if raw_start < 0 or raw_start >= video_duration:
            print(f"[Cutter] ⚠️ Geçersiz başlangıç ({raw_start}s), sıfırlanıyor.")
            raw_start = 0.0
        if raw_end <= raw_start or raw_end > video_duration:
            print(f"[Cutter] ⚠️ Geçersiz bitiş ({raw_end}s), düzeltiliyor.")
            raw_end = min(raw_start + 45.0, video_duration)

        # PySceneDetect snap
        snapped_start = snap_to_scene(raw_start, scene_cuts, window=2.0)
        snapped_end = snap_to_scene(raw_end, scene_cuts, window=2.0)

        # Padding ekle
        start = max(0.0, snapped_start - PADDING)
        end = min(video_duration, snapped_end + PADDING)
        duration = end - start

        # Süre kontrolü
        if duration > MAX_TOTAL:
            print(f"[Cutter] ⚠️ Klip {i+1} çok uzun ({duration:.1f}s), kırpılıyor.")
            end = start + MAX_TOTAL
            duration = MAX_TOTAL
        if duration < MIN_TOTAL:
            duration = min(MIN_TOTAL, video_duration - start)
            end = start + duration

        # Dosya adı oluşturma (subtitler.py'nin bozulmaması için _start_XXX korunuyor)
        # Gemini'nin hook cümlesini de klasörde anlaşılır olsun diye araya sıkıştırıyoruz
        safe_hook = "".join(c for c in hook_text if c.isalnum() or c in (' ', '_')).rstrip().replace(" ", "_")[:20]
        start_tag = f"_start_{int(raw_start)}"
        out_path = str(job_dir / f"clip_{str(i+1).zfill(2)}_{safe_hook}{start_tag}.mp4")

        print(f"[Cutter] Klip {i+1} İşleniyor: {start:.1f}s → {end:.1f}s ({duration:.1f}s)")

        # Mac hızlandırması eklenmiş FFmpeg komutu
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", mp4_path,
            "-t", str(duration),
            "-avoid_negative_ts", "make_zero",
            "-map", "0:v:0",
            "-map", "0:a:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",   # Mac işlemcisini hızlandırır
            "-crf", "18",             # Kayıpsız kalite
            "-threads", "0",          # Tüm işlemci çekirdeklerini kullanır
            "-c:a", "aac",
            out_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Klip {i+1} kesilirken FFmpeg hatası:\n{result.stderr[:300]}")

        clip_paths.append(out_path)

    return clip_paths