"""
Reframe V2 — Ana Orkestratör

Tüm pipeline adımlarını sırasıyla çağırır ve ReframeResult döndürür.

Pipeline adımları:
  1. Video download (gerekirse)
  2. ffprobe → src_w, src_h, fps, duration_s
  3. detect_scenes() → List[SceneInterval]
  4. PersonAnalyzer.analyze_scenes() → List[SceneAnalysis]
  5. get_speaker_segments() → diarization verileri
  6. match_speakers_to_persons() + build_speaker_timeline()
  7. classify_content() → ContentType
  8. Strateji seçimi + generate_decisions()
  9. generate_keyframes() → ReframeResult

Eski sistem dosyaları (scene_detector.py, person_detector.py, composition.py,
crop_calculator.py, strategies/podcast.py eski hali) devre dışı bırakıldı.
Bu processor yalnızca V2 modüllerini kullanır.
"""
import json
import os
import subprocess
import uuid
from typing import Callable, Optional

import requests

from app.config import settings
from app.reframe.analyzers.scene_analyzer import detect_scenes
from app.reframe.analyzers.person_analyzer import PersonAnalyzer
from app.reframe.analyzers.speaker_analyzer import (
    match_speakers_to_persons,
    build_speaker_timeline,
)
from app.reframe.analyzers.content_classifier import classify_content
from app.reframe.strategies.podcast import PodcastStrategy
from app.reframe.strategies.single_speaker import SingleSpeakerStrategy
from app.reframe.strategies.gaming import GamingStrategy
from app.reframe.strategies.generic import GenericStrategy
from app.reframe.composition.keyframe_generator import generate_keyframes
from app.reframe.diarization import get_speaker_segments
from app.reframe.models.types import (
    ContentType,
    ReframeResult,
    TrackingMode,
)
from app.reframe.utils.coord_utils import parse_aspect_ratio


# ─── Strateji Haritası ────────────────────────────────────────────────────────

STRATEGY_MAP = {
    ContentType.PODCAST: PodcastStrategy,
    ContentType.SINGLE_SPEAKER: SingleSpeakerStrategy,
    ContentType.GAMING: GamingStrategy,
    ContentType.GENERIC: GenericStrategy,
}


# ─── Ana Pipeline ─────────────────────────────────────────────────────────────

def run_reframe(
    clip_url: Optional[str] = None,
    clip_local_path: Optional[str] = None,
    clip_id: Optional[str] = None,
    job_id: Optional[str] = None,
    clip_start: float = 0.0,
    clip_end: Optional[float] = None,
    strategy: str = "podcast",
    aspect_ratio: str = "9:16",
    tracking_mode: str = "x_only",
    content_type_hint: Optional[str] = None,
    on_progress: Optional[Callable[[str, int], None]] = None,
) -> ReframeResult:
    """
    V2 reframe pipeline'ını çalıştır. ReframeResult döndürür.

    Args:
        clip_url: Uzak video URL'i (R2, YouTube vb.)
        clip_local_path: Lokal video dosya yolu (upload sonrası)
        clip_id: Supabase clip ID (reframe_metadata için)
        job_id: Pipeline job ID (diarization verisi için)
        clip_start: Klibin video içindeki başlangıç zamanı (saniye)
        clip_end: Klibin video içindeki bitiş zamanı (saniye, None = tam video)
        strategy: Strateji hintti ("podcast", "single", "gaming", "generic")
                  content_type_hint olarak kullanılır (auto-detect + override)
        aspect_ratio: Hedef aspect ratio string ("9:16", "1:1", "4:5", "16:9")
        tracking_mode: "x_only" veya "dynamic_xy"
        content_type_hint: Açık içerik türü override ("auto" veya None = otomatik)
        on_progress: (step_label, percent) callback
    """
    if not clip_url and not clip_local_path:
        raise ValueError("clip_url veya clip_local_path zorunlu")

    def progress(step: str, pct: int) -> None:
        print(f"[Reframe] {pct}% — {step}")
        if on_progress:
            on_progress(step, pct)

    # content_type_hint: açık kullanıcı seçimi yoksa strategy parametresini kullan
    effective_hint = content_type_hint or (strategy if strategy != "auto" else None)

    # Aspect ratio parse
    ar_tuple = parse_aspect_ratio(aspect_ratio)

    # Tracking mode
    try:
        tracking = TrackingMode(tracking_mode)
    except ValueError:
        print(f"[Reframe] Geçersiz tracking_mode '{tracking_mode}' — x_only kullanılıyor")
        tracking = TrackingMode.X_ONLY

    temp_path: Optional[str] = None

    # Input path çözümle
    if clip_local_path and os.path.exists(clip_local_path):
        input_path = clip_local_path
    else:
        temp_path = os.path.join(
            str(settings.UPLOAD_DIR),
            f"reframe_{uuid.uuid4().hex}.mp4",
        )
        input_path = temp_path

    try:
        # ── 1. Video İndir ────────────────────────────────────────────────────
        if temp_path:
            progress("Downloading video...", 5)
            _download_video(clip_url, temp_path)

        # ── 2. Video Metadata ─────────────────────────────────────────────────
        progress("Reading video metadata...", 8)
        src_w, src_h, fps, duration_s = _probe_video(input_path)
        print(f"[Reframe] {src_w}x{src_h} @ {fps:.2f}fps, {duration_s:.2f}s")

        effective_end = clip_end if clip_end is not None else duration_s

        # ── 3. Sahne Tespiti ──────────────────────────────────────────────────
        progress("Detecting scene cuts...", 12)
        # Podcast/talk show için SSIM doğrulamasını atla:
        # Aynı stüdyo farklı kamera açıları → SSIM her zaman 0.94+ → gerçek kesimler reddediliyor
        skip_ssim = (effective_hint or "generic") in ("podcast", "single")
        scenes = detect_scenes(
            input_path,
            content_hint=effective_hint or "generic",
            fps=fps,
            skip_ssim=skip_ssim,
        )
        print(f"[Reframe] {len(scenes)} sahne tespit edildi")
        for s in scenes:
            print(f"[Reframe]   Sahne {s.start_s:.2f}-{s.end_s:.2f}s ({s.duration_s:.2f}s)")

        # ── 4. Multi-Frame Kişi Tespiti ───────────────────────────────────────
        progress("Detecting persons (multi-frame)...", 20)
        analyzer = PersonAnalyzer()
        scene_analyses = analyzer.analyze_scenes(
            input_path, scenes, fps, src_w, src_h
        )
        total_frames = sum(len(sa.frame_analyses) for sa in scene_analyses)
        print(f"[Reframe] {total_frames} frame analiz edildi")

        # ── 5. Diarization ────────────────────────────────────────────────────
        progress("Loading speaker data...", 50)
        speaker_segments: list = []
        if job_id:
            try:
                speaker_segments = get_speaker_segments(job_id, clip_start, effective_end)
                print(f"[Reframe] {len(speaker_segments)} diarization segmenti yüklendi")
            except Exception as e:
                print(f"[Reframe] Diarization yüklenemedi: {e} — visual-only moda devam")
        else:
            print("[Reframe] job_id yok — visual-only mod")

        # ── 6. Konuşmacı-Kişi Eşleştirme ─────────────────────────────────────
        progress("Matching speakers to persons...", 58)
        speaker_person_map = match_speakers_to_persons(
            scene_analyses, speaker_segments, src_w
        )
        speaker_timeline = build_speaker_timeline(
            speaker_segments,
            speaker_person_map,
            min_speech_duration_s=0.8,
        )

        # ── 7. İçerik Türü Sınıflandırma ─────────────────────────────────────
        progress("Classifying content type...", 62)
        content_type = classify_content(
            scene_analyses, speaker_segments, effective_hint
        )
        print(f"[Reframe] İçerik türü: {content_type.value}")

        # ── 8. Strateji Seçimi ve Karar Üretimi ──────────────────────────────
        progress("Applying reframe strategy...", 65)
        strategy_class = STRATEGY_MAP.get(content_type, GenericStrategy)
        strategy_instance = strategy_class(tracking_mode=tracking)

        decisions = strategy_instance.generate_decisions(
            scene_analyses=scene_analyses,
            speaker_person_map=speaker_person_map,
            speaker_timeline=speaker_timeline,
            src_w=src_w,
            src_h=src_h,
            aspect_ratio=ar_tuple,
        )
        total_segments = sum(len(d.segments) for d in decisions)
        print(f"[Reframe] {total_segments} reframe segmenti üretildi")

        # ── 9. Keyframe Üretimi ───────────────────────────────────────────────
        progress("Generating keyframes...", 80)
        result = generate_keyframes(
            decisions=decisions,
            src_w=src_w,
            src_h=src_h,
            fps=fps,
            duration_s=duration_s,
            content_type=content_type,
            tracking_mode=tracking,
            aspect_ratio=ar_tuple,
            config=strategy_instance.config,
        )

        progress("Done!", 100)
        print(
            f"[Reframe] Tamamlandı — "
            f"{len(result.keyframes)} keyframe, "
            f"{len(result.scene_cuts)} scene cut"
        )
        return result

    except Exception as e:
        print(f"[Reframe] Pipeline hatası: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


# ─── Video Yardımcıları ───────────────────────────────────────────────────────

def _probe_video(video_path: str) -> tuple[int, int, float, float]:
    """
    ffprobe ile video boyutları, FPS ve süresini al.
    Returns: (src_w, src_h, fps, duration_s)
    """
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        video_path,
    ]
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe hatası: {result.stderr[:200]}")

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError("ffprobe video stream bulamadı")

    stream = streams[0]
    src_w = int(stream.get("width", 0))
    src_h = int(stream.get("height", 0))

    if src_w == 0 or src_h == 0:
        raise RuntimeError(f"Geçersiz video boyutu: {src_w}x{src_h}")

    # FPS: "30/1" veya "2997/100" formatından hesapla
    r_frame_rate = stream.get("r_frame_rate", "30/1")
    try:
        num, den = r_frame_rate.split("/")
        fps = float(num) / float(den)
    except Exception:
        fps = 30.0

    # Süre: stream → format fallback
    duration_s = float(stream.get("duration", 0.0))
    if duration_s == 0.0:
        cmd2 = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ]
        r2 = subprocess.run(
            cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=30,
        )
        if r2.returncode == 0:
            fmt = json.loads(r2.stdout).get("format", {})
            duration_s = float(fmt.get("duration", 0.0))

    if duration_s == 0.0:
        raise RuntimeError("Video süresi belirlenemedi")

    return src_w, src_h, round(fps, 4), round(duration_s, 4)


def _download_video(url: str, dest_path: str) -> None:
    """Uzak videoyu dest_path'e indir. FFmpeg başarısız olursa requests ile dene."""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", url,
            "-c", "copy",
            dest_path,
        ]
        subprocess.run(
            cmd, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=300,
        )
    except subprocess.CalledProcessError:
        # HTTP fallback (R2 presigned URL, vs.)
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
