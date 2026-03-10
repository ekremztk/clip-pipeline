"""
pipeline.py
-----------
Tüm modülleri birbirine bağlar.
Sıra: İndir → Transkript → Ses Analizi → AI Analiz → Kes → Reframe → Altyazı → Rapor
"""

import traceback
from state import jobs
from downloader import download_video
from transcriber import transcribe
from audio_analyzer import analyze_energy
from analyzer import analyze_audio
from cutter import cut_clips
# from reframer import reframe_to_vertical, is_already_vertical
# from subtitler import generate_subtitles, burn_subtitles
from pdf_reporter import write_pdf_report
from metadata import write_metadata


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
            transcript = transcribe(mp3_path, language="tr")
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
        update(job_id, "running", "AI analizi yapılıyor (4 ajanlı sistem)...", 35)
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

        # ── AŞAMA 3: Video Kesme ──────────────────────────────────────────────
        update(job_id, "running", "Klipler kesiliyor...", 55)
        clip_paths = cut_clips(mp4_path, clips_data, job_id)

        # ── AŞAMA 4: Dikey Format (9:16) ──────────────────────────────────────
        # update(job_id, "running", "9:16 dikey formata çevriliyor...", 68)
        # vertical_paths = []
        # for clip_path in clip_paths:
        #     if is_already_vertical(clip_path):
        #         print(f"[Pipeline] Zaten dikey: {clip_path}")
        #         vertical_paths.append(clip_path)
        #     else:
        #         vertical_path = clip_path.replace(".mp4", "_vertical.mp4")
        #         result = reframe_to_vertical(clip_path, vertical_path)
        #         vertical_paths.append(result)

        # ── AŞAMA 5: Altyazı Üretimi ─────────────────────────────────────────
        # update(job_id, "running", "Altyazılar oluşturuluyor...", 78)
        # srt_paths = generate_subtitles(
        #     vertical_paths, job_id,
        #     transcript=transcript,
        #     channel_id=channel_id
        # )

        # ── AŞAMA 5B: Altyazı Yakma (burn-in) ────────────────────────────────
        # update(job_id, "running", "Altyazılar videoya ekleniyor...", 85)
        # final_paths = []
        # for i, (vpath, srt_path) in enumerate(zip(vertical_paths, srt_paths)):
        #     final_path = vpath.replace("_vertical.mp4", "_final.mp4").replace(".mp4", "_final.mp4")
        #     if final_path == vpath:
        #         final_path = vpath.replace(".mp4", "_subtitled.mp4")
        #     burned = burn_subtitles(vpath, srt_path, final_path, channel_id)
        #     final_paths.append(burned)

        # ── AŞAMA 6: Raporlar ────────────────────────────────────────────────
        update(job_id, "running", "Raporlar hazırlanıyor...", 95)
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
                    # Sadece Kesilmiş Ham Video (16:9)
                    "mp4": f"/output/{job_id}/{_basename(clip_paths[i])}",
                    "srt": "", # Artık otomatik altyazı üretmiyoruz
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
