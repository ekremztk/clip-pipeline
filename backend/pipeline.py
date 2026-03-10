"""
pipeline.py
-----------
Sıra: İndir → Transkript → Ses Analizi → AI Analiz (İngilizce) → Yatay Kesim → Rapor
NOT: Dikey yapma ve Altyazı ekleme işlemleri Aşama 2 (Editör) için devredışı bırakıldı.
"""

import traceback
from state import jobs
from downloader import download_video
from transcriber import transcribe
from audio_analyzer import analyze_energy
from analyzer import analyze_audio
from cutter import cut_clips
from pdf_reporter import write_pdf_report
from metadata import write_metadata

# Aşama 2 modülleri şimdilik import edilmiyor (Sunucuyu yormamak için)
# from reframer import reframe_to_vertical, is_already_vertical
# from subtitler import generate_subtitles, burn_subtitles

def update(job_id: str, status: str, step: str, progress: int):
    jobs[job_id]["status"] = status
    jobs[job_id]["step"] = step
    jobs[job_id]["progress"] = progress


def run_pipeline(job_id: str, url: str, clip_count: int, channel_id: str = "default"):
    try:
        # ── AŞAMA 0: İndirme ─────────────────────────────────────────────────
        update(job_id, "running", "Video indiriliyor...", 5)
        mp4_path, mp3_path, video_title = download_video(url, job_id)

        # ── AŞAMA 1A: WhisperX Transkript ────────────────────────────────────
        update(job_id, "running", "Ses transkribe ediliyor (WhisperX)...", 15)
        try:
            transcript = transcribe(mp3_path, language="en") # Hedef içerik İngilizce olduğu için
        except Exception as e:
            print(f"[Pipeline] Transkript hatası: {e}, devam ediliyor...")
            transcript = None

        # ── AŞAMA 1B: Ses Enerji Analizi ─────────────────────────────────────
        update(job_id, "running", "Ses enerjisi analiz ediliyor...", 25)
        try:
            audio_energy = analyze_energy(mp3_path)
        except Exception as e:
            print(f"[Pipeline] Ses analizi hatası: {e}, devam ediliyor...")
            audio_energy = None

        # ── AŞAMA 2: 4 Ajanlı AI Analizi ─────────────────────────────────────
        update(job_id, "running", "AI analizi yapılıyor (İngilizce 4 ajan)...", 35)
        clips_data = analyze_audio(
            mp3_path=mp3_path,
            clip_count=clip_count,
            video_title=video_title,
            transcript=transcript,
            audio_energy=audio_energy,
            channel_id=channel_id
        )

        if not clips_data:
            raise RuntimeError("AI bu videoda viral klip bulamadı.")

        # ── AŞAMA 3: Video Kesme (Orijinal 16:9 Formatında) ───────────────────
        update(job_id, "running", "Klipler orijinal yatay formatta kesiliyor...", 55)
        clip_paths = cut_clips(mp4_path, clips_data, job_id)

        # ── AŞAMA 4 & 5 İPTAL EDİLDİ (Editör Aşamasında Yapılacak) ───────────
        # Dikey Formata Çevirme ve Altyazı Ekleme Kodları buradan kaldırıldı.

        # ── AŞAMA 6: Raporlar ────────────────────────────────────────────────
        update(job_id, "running", "İngilizce raporlar hazırlanıyor...", 90)
        write_pdf_report(clips_data, job_id, video_title)
        write_metadata(clips_data, job_id, video_title)

        # ── TAMAMLANDI ────────────────────────────────────────────────────────
        jobs[job_id]["status"] = "done"
        jobs[job_id]["step"] = "Tamamlandı"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["result"] = {
            "title": video_title,
            "job_id": job_id,
            "pdf": f"/output/{job_id}/report.pdf",
            "clips": [
                {
                    "index": i + 1,
                    "title": clips_data[i].get("title", ""),
                    "description": clips_data[i].get("description", ""),
                    "hashtags": clips_data[i].get("hashtags", ""),
                    "start": clips_data[i]["start_sec"],
                    "end": clips_data[i]["end_sec"],
                    "score": clips_data[i].get("score"),
                    "clip_text": clips_data[i].get("clip_text"),
                    "trim_note": clips_data[i].get("recommendation"),
                    "why_selected": clips_data[i].get("why_selected"),
                    "recommendation": clips_data[i].get("recommendation"),
                    "bolum_analizi": clips_data[i].get("bolum_analizi", []),
                    "puanlar": clips_data[i].get("puanlar", {}),
                    "guest_name": clips_data[i].get("guest_name", ""),
                    
                    # Artık dikey/altyazılı final videosu yerine, direkt ham yatay kesimi (clip_paths) sunuyoruz
                    "mp4": f"/output/{job_id}/{_basename(clip_paths[i])}",
                    "srt": "", # Otomatik altyazı yok
                }
                for i in range(len(clips_data))
            ],
        }

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["step"] = f"Hata: {str(e)[:80]}"
        traceback.print_exc()

def _basename(path: str) -> str:
    from pathlib import Path
    return Path(path).name