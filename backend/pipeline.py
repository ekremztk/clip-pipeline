"""
pipeline.py (V1.5 - Full Integration)
--------------------------------------
Tüm modüller bağlı orkestratör:
1. Audio Extraction (FFmpeg)
2. Transcription (Groq Whisper → Gemini fallback)
3. Audio Energy Analysis (Librosa)
4. RAG + Gemini Analysis (transkript + enerji verisi ile zenginleştirilmiş)
5. Schema Validation
6. Precision Cut (PySceneDetect + FFmpeg)
7. Report Generation (metadata.txt + report.pdf)
"""

import os
import subprocess
import traceback
from pathlib import Path

from state import jobs
from analyzer import analyze_video_for_clips
from cutter import cut_clips


def update(job_id: str, status: str, step: str, progress: int):
    if job_id in jobs:
        jobs[job_id]["status"] = status
        jobs[job_id]["step"] = step
        jobs[job_id]["progress"] = progress


def run_pipeline(job_id: str, local_mp4_path: str, video_title: str, video_description: str):
    audio_path = f"temp_{job_id}.m4a"
    
    # Pipeline boyunca paylaşılan veriler
    transcript = None
    energy_data = None
    
    try:
        # ═══════════════════════════════════════════════════════════════
        # ADIM 1: Audio Extraction (FFmpeg)
        # ═══════════════════════════════════════════════════════════════
        update(job_id, "running", "Ses verisi ayıklanıyor...", 5)
        
        command = [
            "ffmpeg", "-y",
            "-i", local_mp4_path,
            "-vn",
            "-acodec", "copy",
            audio_path
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg Hatası: {result.stderr}")
        
        print(f"[Pipeline] ✅ Ses dosyası hazır: {audio_path}")

        # ═══════════════════════════════════════════════════════════════
        # ADIM 2: Transkript (Groq Whisper → Gemini Fallback)
        # ═══════════════════════════════════════════════════════════════
        update(job_id, "running", "Konuşma metne dönüştürülüyor (Whisper)...", 15)
        
        transcript_text = ""
        try:
            from transcriber import transcribe, format_transcript_for_gemini
            
            transcript = transcribe(audio_path)
            
            if transcript and transcript.get("segments"):
                transcript_text = format_transcript_for_gemini(transcript)
                word_count = len(transcript.get("full_text", "").split())
                print(f"[Pipeline] ✅ Transkript hazır: {len(transcript['segments'])} segment, {word_count} kelime")
            else:
                print("[Pipeline] ⚠️ Transkript boş döndü, Gemini salt ses ile devam edecek.")
                
        except Exception as e:
            print(f"[Pipeline] ⚠️ Transkript modülü hatası: {e}")
            print("[Pipeline] Gemini salt ses analizi ile devam ediyor...")

        # ═══════════════════════════════════════════════════════════════
        # ADIM 3: Ses Enerji Analizi (Librosa)
        # ═══════════════════════════════════════════════════════════════
        update(job_id, "running", "Ses enerji haritası çıkarılıyor (Librosa)...", 25)
        
        energy_summary = ""
        try:
            from audio_analyzer import analyze_energy
            
            energy_data = analyze_energy(audio_path)
            
            if energy_data and energy_data.get("summary"):
                energy_summary = energy_data["summary"]
                peak_count = len(energy_data.get("energy_peaks", []))
                silence_count = len(energy_data.get("silence_zones", []))
                print(f"[Pipeline] ✅ Enerji analizi hazır: {peak_count} zirve, {silence_count} sessizlik")
            else:
                print("[Pipeline] ⚠️ Enerji analizi boş döndü, Gemini enerjisiz devam edecek.")
                
        except Exception as e:
            print(f"[Pipeline] ⚠️ Enerji analizi modülü hatası: {e}")
            print("[Pipeline] Gemini enerji verisi olmadan devam ediyor...")

        # ═══════════════════════════════════════════════════════════════
        # ADIM 4: RAG + Gemini Analizi (Zenginleştirilmiş Bağlam)
        # ═══════════════════════════════════════════════════════════════
        update(job_id, "running", "RAG & Gemini Viral Analizi yapılıyor...", 40)
        
        full_context = f"Title: {video_title}\nDescription: {video_description}"
        
        clips_data = analyze_video_for_clips(
            audio_path=audio_path,
            video_title=full_context,
            transcript_text=transcript_text,
            energy_summary=energy_summary
        )

        if not clips_data:
            raise RuntimeError("Yapay zeka bu videoda kriterlere uygun viral klip bulamadı.")
        
        print(f"[Pipeline] ✅ {len(clips_data)} klip doğrulandı ve onaylandı.")

        # ═══════════════════════════════════════════════════════════════
        # ADIM 5: PySceneDetect & Precision Cut
        # ═══════════════════════════════════════════════════════════════
        update(job_id, "running", "Doğal sahne geçişleri saptanıyor ve kesiliyor...", 60)
        
        clip_paths = cut_clips(local_mp4_path, clips_data, job_id)
        
        print(f"[Pipeline] ✅ {len(clip_paths)} klip kesildi.")

        # ═══════════════════════════════════════════════════════════════
        # ADIM 6: Rapor Üretimi (Metadata + PDF)
        # ═══════════════════════════════════════════════════════════════
        update(job_id, "running", "Raporlar üretiliyor (TXT + PDF)...", 85)
        
        report_data = None
        metadata_path = None
        pdf_path = None
        
        try:
            from report_builder import build_report_data
            
            report_data = build_report_data(clips_data, transcript)
            print(f"[Pipeline] ✅ Rapor verisi hazırlandı: {len(report_data)} klip")
            
            # Metadata TXT
            try:
                from metadata import write_metadata
                metadata_path = write_metadata(report_data, job_id, video_title)
                print(f"[Pipeline] ✅ Metadata TXT: {metadata_path}")
            except Exception as e:
                print(f"[Pipeline] ⚠️ Metadata TXT üretilemedi: {e}")
            
            # PDF Rapor
            try:
                from pdf_reporter import write_pdf_report
                pdf_path = write_pdf_report(report_data, job_id, video_title)
                print(f"[Pipeline] ✅ PDF Rapor: {pdf_path}")
            except Exception as e:
                print(f"[Pipeline] ⚠️ PDF rapor üretilemedi: {e}")
                
        except Exception as e:
            print(f"[Pipeline] ⚠️ Rapor modülleri yüklenemedi: {e}")
            print("[Pipeline] Raporlar olmadan devam ediliyor...")

        # ═══════════════════════════════════════════════════════════════
        # SONUÇLARI HAZIRLA
        # ═══════════════════════════════════════════════════════════════
        
        # Sonuç verisini hem Gemini raw çıktısı hem report formatından zenginleştir
        result_clips = []
        for i in range(len(clip_paths)):
            clip_result = {
                "index": i + 1,
                "hook": clips_data[i].get("hook_text"),
                "score": clips_data[i].get("virality_score"),
                "psychological_trigger": clips_data[i].get("psychological_trigger"),
                "rag_reference_used": clips_data[i].get("rag_reference_used"),
                "path": f"/{clip_paths[i]}",
            }
            
            # Report data varsa ek alanları da ekle
            if report_data and i < len(report_data):
                clip_result["suggested_title"] = report_data[i].get("title", "")
                clip_result["suggested_description"] = report_data[i].get("description", "")
                clip_result["suggested_hashtags"] = report_data[i].get("hashtags", "")
                clip_result["why_selected"] = report_data[i].get("why_selected", "")
                clip_result["transcript_excerpt"] = report_data[i].get("transcript", "")
            
            result_clips.append(clip_result)
        
        jobs[job_id]["status"] = "done"
        jobs[job_id]["step"] = "Modül 1 Tamamlandı"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["result"] = {
            "original_title": video_title,
            "clips_count": len(clip_paths),
            "clips": result_clips,
            # Rapor dosya yolları (frontend indirme butonu için)
            "metadata_path": f"/{metadata_path}" if metadata_path else None,
            "pdf_path": f"/{pdf_path}" if pdf_path else None,
        }
        
        print(f"[Pipeline] ✅✅✅ İŞLEM TAMAMLANDI — {len(clip_paths)} klip, raporlar hazır.")

    except Exception as e:
        update(job_id, "error", f"Hata: {str(e)}", 0)
        traceback.print_exc()

    finally:
        # Geçici dosya temizliği — Railway diskini korur
        if os.path.exists(audio_path):
            os.remove(audio_path)
            print(f"[Pipeline] 🧹 Geçici ses dosyası silindi: {audio_path}")
        if os.path.exists(local_mp4_path):
            os.remove(local_mp4_path)
            print(f"[Pipeline] 🧹 Geçici video dosyası silindi: {local_mp4_path}")