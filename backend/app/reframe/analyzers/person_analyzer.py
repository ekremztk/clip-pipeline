"""
Reframe V2 — Multi-Frame Kişi Tespiti ve Takibi

Mevcut sistemden temel fark:
  Eski sistem → her sahnenin SADECE ilk frame'ini analiz ediyordu.
  Yeni sistem → her sahne için birden fazla frame analiz eder, frame'ler
                arası IoU ile kişi eşleştirmesi yaparak trajectory üretir.

Bu sayede:
  - Sahne boyunca kişi hareketi takip edilir
  - Kişi frame dışına çıkarsa önceki pozisyon korunur
  - Crop hedefi daha kararlı (tek frame noise'ından etkilenmez)
"""
from typing import Optional

import cv2
import numpy as np

from ..models.types import (
    BBox,
    FrameAnalysis,
    PersonDetection,
    PersonTrajectory,
    SceneAnalysis,
    SceneInterval,
)


# ─── Sabitler ─────────────────────────────────────────────────────────────────

CONFIDENCE_THRESHOLD = 0.50      # YOLOv8 güven eşiği
IOU_MATCH_THRESHOLD = 0.30       # Frame'ler arası kişi eşleştirme minimum IoU
MAX_PERSONS_PER_FRAME = 4        # Frame başına maksimum kişi sayısı
ANALYSIS_RESOLUTION = (640, 360) # YOLOv8 inference için küçültme boyutu

# Filtreleme eşikleri (normalize 0-1)
MIN_PERSON_HEIGHT = 0.15         # Kişi en az frame yüksekliğinin %15'i olmalı
MIN_PERSON_WIDTH = 0.04          # Kişi en az frame genişliğinin %4'ü olmalı
MAX_BOTTOM_MARGIN = 0.92         # Kişi bbox'ı frame'in %92'sinden aşağıda olamaz
MIN_TOP_MARGIN = 0.03            # Kişi bbox'ı frame'in %3'ünden yukarıda olamaz


# ─── PersonAnalyzer Sınıfı ────────────────────────────────────────────────────

class PersonAnalyzer:
    """
    Multi-frame kişi tespiti ve IoU bazlı trajectory takibi.

    YOLOv8 nano-pose modeli kullanır (CPU'da yeterli hız).
    Her sahne için sahne süresine göre akıllı örnekleme yapar.
    """

    def __init__(self, model_path: str = "yolov8n-pose.pt"):
        try:
            from ultralytics import YOLO
            self._model = YOLO(model_path)
            print(f"[PersonAnalyzer] Model yüklendi: {model_path}")
        except Exception as e:
            print(f"[PersonAnalyzer] Model yükleme hatası: {e}")
            self._model = None

    def analyze_scenes(
        self,
        video_path: str,
        scenes: list[SceneInterval],
        fps: float,
        src_w: int,
        src_h: int,
    ) -> list[SceneAnalysis]:
        """
        Tüm sahneleri analiz et ve SceneAnalysis listesi döndür.

        Her sahne için:
        1. Örnekleme zamanlarını belirle (süreye göre)
        2. Her frame'i analiz et
        3. IoU ile kişi tracking yap
        4. PersonTrajectory listesi oluştur
        """
        if self._model is None:
            print("[PersonAnalyzer] Model yok — boş analiz döndürülüyor")
            return [
                SceneAnalysis(
                    scene=s,
                    frame_analyses=[],
                    trajectories=[],
                    person_count=0,
                )
                for s in scenes
            ]

        results = []
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            print("[PersonAnalyzer] Video açılamadı")
            cap.release()
            return [
                SceneAnalysis(
                    scene=s,
                    frame_analyses=[],
                    trajectories=[],
                    person_count=0,
                )
                for s in scenes
            ]

        try:
            total_frames_analyzed = 0
            for scene_idx, scene in enumerate(scenes):
                try:
                    analysis = self._analyze_scene(cap, scene, fps, src_w, src_h)
                    results.append(analysis)
                    total_frames_analyzed += len(analysis.frame_analyses)
                    print(
                        f"[PersonAnalyzer] Sahne {scene_idx + 1}/{len(scenes)}: "
                        f"{len(analysis.frame_analyses)} frame, "
                        f"{analysis.person_count} kişi"
                    )
                except Exception as e:
                    print(f"[PersonAnalyzer] Sahne {scene_idx + 1} hatası: {e}")
                    results.append(SceneAnalysis(
                        scene=scene,
                        frame_analyses=[],
                        trajectories=[],
                        person_count=0,
                    ))

            print(
                f"[PersonAnalyzer] Tamamlandı — "
                f"toplam {total_frames_analyzed} frame analiz edildi"
            )
        finally:
            cap.release()

        return results

    def _analyze_scene(
        self,
        cap: cv2.VideoCapture,
        scene: SceneInterval,
        fps: float,
        src_w: int,
        src_h: int,
    ) -> SceneAnalysis:
        """Tek bir sahneyi multi-frame analiz et."""
        sample_times = self._get_sample_times(scene, fps)
        print(f"[PersonAnalyzer] Sahne {scene.start_s:.2f}-{scene.end_s:.2f}s: {len(sample_times)} frame örnekleniyor")
        print(f"[PersonAnalyzer] Sample times: {[round(t, 2) for t in sample_times]}")

        frame_analyses: list[FrameAnalysis] = []
        for i, time_s in enumerate(sample_times):
            frame = self._extract_frame(cap, time_s)
            if frame is None:
                print(f"[PersonAnalyzer]   t={time_s:.2f}s: Frame alınamadı")
                continue

            persons = self._detect_persons(frame, src_w, src_h)
            print(f"[PersonAnalyzer]   t={time_s:.2f}s: {len(persons)} kişi tespit edildi")
            for p in persons:
                print(f"[PersonAnalyzer]     bbox=({p.bbox.x:.3f},{p.bbox.y:.3f},{p.bbox.w:.3f},{p.bbox.h:.3f}) head=({p.head_center_x:.3f},{p.head_center_y:.3f}) conf={p.confidence:.2f}")

            frame_analyses.append(FrameAnalysis(
                time_s=time_s,
                persons=persons,
                frame_index=i,
            ))

        # Frame'ler arası IoU kişi eşleştirmesi
        self._assign_person_ids(frame_analyses)

        # Trajectory'leri oluştur
        trajectories = self._build_trajectories(frame_analyses)

        print(f"[PersonAnalyzer] Trajectory sayısı: {len(trajectories)}")
        for t in trajectories:
            print(f"[PersonAnalyzer]   Person {t.person_id}: {len(t.positions)} pozisyon, mean_x={t.mean_x:.3f}, x_range={t.x_range:.3f}, is_static={t.is_static}")

        return SceneAnalysis(
            scene=scene,
            frame_analyses=frame_analyses,
            trajectories=trajectories,
            person_count=len(trajectories),
        )

    # ─── Örnekleme Zamanları ──────────────────────────────────────────────────

    def _get_sample_times(
        self, scene: SceneInterval, fps: float
    ) -> list[float]:
        """
        Sahne süresine göre örnekleme zamanlarını belirle.

        < 1s   → sadece ortası (1 frame)
        < 3s   → baş, orta, son (3 frame)
        3-10s  → 1 fps örnekleme
        > 10s  → 0.5 fps örnekleme
        """
        duration = scene.duration_s
        offset = 0.05  # Sahne sınırındaki artefaktları atla

        if duration < 1.0:
            return [scene.start_s + duration / 2]

        if duration < 3.0:
            return [
                scene.start_s + offset,
                scene.start_s + duration / 2,
                scene.end_s - offset,
            ]

        sample_fps = 1.0 if duration <= 10.0 else 0.5
        step = 1.0 / sample_fps

        times = []
        t = scene.start_s + offset
        while t < scene.end_s - offset:
            times.append(t)
            t += step

        # Son frame'i de ekle (eğer yeterince uzaksa)
        last_t = scene.end_s - offset
        if not times or (last_t - times[-1]) > step * 0.5:
            times.append(last_t)

        return times

    # ─── Frame Extraction ─────────────────────────────────────────────────────

    def _extract_frame(
        self, cap: cv2.VideoCapture, time_s: float
    ) -> Optional[np.ndarray]:
        """VideoCapture'dan belirli zamandaki frame'i al."""
        cap.set(cv2.CAP_PROP_POS_MSEC, time_s * 1000)
        ret, frame = cap.read()
        return frame if ret else None

    # ─── YOLOv8 Kişi Tespiti ──────────────────────────────────────────────────

    def _detect_persons(
        self,
        frame: np.ndarray,
        src_w: int,
        src_h: int,
    ) -> list[PersonDetection]:
        """
        YOLOv8 nano-pose ile kişileri tespit et.

        Filtreler:
        - Confidence > 0.50
        - Bbox yüksekliği > frame'in %15'i
        - Bbox genişliği > frame'in %4'ü
        - Bbox alt kenarı > frame'in %3'ü (ekranın çok tepesinde değil)
        - Bbox alt kenarı < frame'in %92'si (ekranın çok altında değil)
        """
        try:
            # Küçült (hız için)
            small = cv2.resize(frame, ANALYSIS_RESOLUTION)
            scale_x = src_w / ANALYSIS_RESOLUTION[0]
            scale_y = src_h / ANALYSIS_RESOLUTION[1]

            results = self._model(small, verbose=False, conf=CONFIDENCE_THRESHOLD)
            detections: list[PersonDetection] = []

            for result in results:
                if result.boxes is None:
                    continue

                boxes = result.boxes
                keypoints_data = result.keypoints

                for i in range(len(boxes)):
                    # Sadece person (class 0)
                    if int(boxes.cls[i]) != 0:
                        continue

                    # Bbox koordinatlarını normalize et
                    x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()

                    # Scale back to original size, then normalize
                    x1_orig = x1 * scale_x
                    y1_orig = y1 * scale_y
                    x2_orig = x2 * scale_x
                    y2_orig = y2 * scale_y

                    bbox = BBox(
                        x=float(x1_orig / src_w),
                        y=float(y1_orig / src_h),
                        w=float((x2_orig - x1_orig) / src_w),
                        h=float((y2_orig - y1_orig) / src_h),
                    )

                    # Boyut filtreleri
                    if bbox.h < MIN_PERSON_HEIGHT:
                        continue
                    if bbox.w < MIN_PERSON_WIDTH:
                        continue
                    # Çok yukarıda veya çok aşağıda olanları çıkar
                    if bbox.y < MIN_TOP_MARGIN and bbox.y + bbox.h < 0.10:
                        continue
                    if bbox.y + bbox.h > MAX_BOTTOM_MARGIN:
                        continue

                    # Pose keypoints normalize et
                    pose_kps: list[tuple[float, float, float]] = []
                    if keypoints_data is not None and i < len(keypoints_data.data):
                        kps = keypoints_data.data[i].cpu().numpy()
                        for kp in kps:
                            kp_x = float(kp[0] * scale_x / src_w)
                            kp_y = float(kp[1] * scale_y / src_h)
                            kp_conf = float(kp[2]) if len(kp) > 2 else 0.0
                            pose_kps.append((kp_x, kp_y, kp_conf))

                    detections.append(PersonDetection(
                        bbox=bbox,
                        confidence=float(boxes.conf[i]),
                        pose_keypoints=pose_kps,
                    ))

            # Confidence'a göre sırala, MAX_PERSONS tane al
            detections.sort(key=lambda d: d.confidence, reverse=True)
            return detections[:MAX_PERSONS_PER_FRAME]

        except Exception as e:
            print(f"[PersonAnalyzer] Kişi tespiti hatası: {e}")
            return []

    # ─── IoU Kişi Eşleştirme ─────────────────────────────────────────────────

    def _assign_person_ids(self, frame_analyses: list[FrameAnalysis]) -> None:
        """
        Frame'ler arası kişi eşleştirmesi — IoU bazlı.

        İlk frame'deki kişilere 0'dan başlayarak ID ata.
        Sonraki her frame için:
          - Önceki frame'deki kişilerle IoU hesapla
          - IoU > threshold → aynı kişi, ID'yi koru
          - Eşleşme yoksa → yeni ID ata (yeni kişi girdi)
        """
        if not frame_analyses:
            return

        # İlk frame'e ID ata
        for i, person in enumerate(frame_analyses[0].persons):
            person.person_id = i

        next_id = len(frame_analyses[0].persons)

        # Sonraki frame'leri eşleştir
        for f_idx in range(1, len(frame_analyses)):
            prev_persons = frame_analyses[f_idx - 1].persons
            curr_persons = frame_analyses[f_idx].persons

            used_prev_ids: set[int] = set()

            for curr in curr_persons:
                best_iou = 0.0
                best_prev_id: Optional[int] = None

                for prev in prev_persons:
                    if prev.person_id is None or prev.person_id in used_prev_ids:
                        continue
                    iou = curr.bbox.iou(prev.bbox)
                    if iou > best_iou and iou >= IOU_MATCH_THRESHOLD:
                        best_iou = iou
                        best_prev_id = prev.person_id

                if best_prev_id is not None:
                    curr.person_id = best_prev_id
                    used_prev_ids.add(best_prev_id)
                else:
                    # Yeni kişi — yeni ID
                    curr.person_id = next_id
                    next_id += 1

    # ─── Trajectory Oluşturma ─────────────────────────────────────────────────

    def _build_trajectories(
        self, frame_analyses: list[FrameAnalysis]
    ) -> list[PersonTrajectory]:
        """
        Frame analizlerinden kişi trajectory'lerini oluştur.

        Kural: En az 2 frame'de görünen kişiler trajectory'e dahil edilir
               (1 frame görünen kişiler gürültü olabilir).
        İstisna: Sahnede sadece 1-2 frame varsa bu kural uygulanmaz.

        Trajectory'ler kafa merkezi (head_center_x/y) kullanır —
        bbox merkezinden daha doğru crop hedefleme sağlar.
        """
        person_positions: dict[int, list[tuple[float, float, float]]] = {}

        for fa in frame_analyses:
            for person in fa.persons:
                if person.person_id is None:
                    continue
                pid = person.person_id
                if pid not in person_positions:
                    person_positions[pid] = []
                person_positions[pid].append((
                    fa.time_s,
                    person.head_center_x,
                    person.head_center_y,
                ))

        trajectories: list[PersonTrajectory] = []
        min_frames = 2 if len(frame_analyses) > 2 else 1

        for pid, positions in person_positions.items():
            if len(positions) >= min_frames:
                trajectories.append(PersonTrajectory(
                    person_id=pid,
                    positions=positions,
                ))

        # Soldan sağa sırala (X pozisyonuna göre)
        # Bu sıralama konuşmacı eşleştirmede kritik:
        # sol = düşük X = genellikle speaker 0 (host)
        trajectories.sort(key=lambda t: t.mean_x)
        return trajectories
