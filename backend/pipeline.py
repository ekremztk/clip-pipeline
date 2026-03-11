"""
pipeline.py (V2.0 - Supabase Integrated)
-----------------------------------------
database.py üzerinden Supabase'e kalıcı yazma.
Supabase bağlantısı yoksa in-memory fallback devreye girer.
"""

import os
import subprocess
import traceback
from pathlib import Path

from database import create_job, update_job, save_clips, get_job
from analyzer import analyze_video_for_clips
from cutter import cut_clips


def update(job_id: str, status: str, step: str, progress: int):
    """Job durumunu günceller (Supabase + fallback)."""
    update_job(job_id, status=status, step=step, progress=progress)


def build_clip_result(clip_raw: dict, clip_path: str, index: int, 
                      report_item: dict = None, transcript: dict = None) -> dict:
    """Tek bir klip için frontend'e gönderilecek sonuç objesini oluşturur."""
    result = {
        "index": index,
        "hook": clip_raw.get("hook_text", ""),
        "score": clip_raw.get("virality_score", 0),
        "psychological_trigger": clip_raw.get("psychological_trigger", ""),
        "rag_reference_used": clip_raw.get("rag_reference_used", ""),
        "path": f"/{clip_path}",
        "suggested_title": clip_raw.get("suggested_title", ""),
        "suggested_description": clip_raw.get("suggested_description", ""),
        "suggested_hashtags": clip_raw.get("suggested_hashtags", ""),
        "why_selected": clip_raw.get("why_selected", ""),
        "audio_energy_note": clip_raw.get("audio_energy_note", ""),
        "trim_note": clip_raw.get("trim_note", ""),
        "transcript_excerpt": "",
    }
    
    if report_item:
        result["suggested_title"] = report_item.get("title", "") or result["suggested_title"]
        result["suggested_description"] = report_item.get("description", "") or result["suggested_description"]
        result["suggested_hashtags"] = report_item.get("hashtags", "") or result["suggested_hashtags"]
        result["why_selected"] = report_item.get("why_selected", "") or result["why_selected"]
        result["transcript_excerpt"] = report_item.get("transcript", "") or ""
    
    if not result["transcript_excerpt"] and transcript and transcript.get("segments"):
        try:
            from transcriber import get_words_in_range
            start = float(clip_raw.get("start_time", 0))
            end = float(clip_raw.get("end_time", 30))
            words = get_words_in_range(transcript, start, end)
            if words:
                result["transcript_excerpt"] = " ".join([w["word"] for w in words])
            else:
                result["transcript_excerpt"] = _extract_segment_text(transcript, start, end)
        except Exception as e:
            print(f"[Pipeline] ⚠️ Transkript çıkarma hatası: {e}")
    
    return result


def _extract_segment_text(transcript: dict, start_sec: float, end_sec: float) -> str:
    texts = []
    for seg in transcript.get("segments", []):
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        if seg_end >= start_sec and seg_start <= end_sec:
            text = seg.get("text", "").strip()
            if text:
                texts.append(text)
    return " ".join(texts)


def run_pipeline(job_id: str, local_mp4_path: str, video_title: str, video_description: str):
    audio_path = f"temp_{job_id}.m4a"
    transcript = None
    
    try:
        # ═══════════════════════════════════════════════════════════════
        # ADIM 1: Audio Extraction
        # ═══════════════════════════════════════════════════════════════
        update(job_id, "running", "Ses verisi ayıklanıyor...", 5)
        
        command = [
            "ffmpeg", "-y", "-i", local_mp4_path,
            "-vn", "-acodec", "copy", audio_path
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg Hatası: {result.stderr}")
        print(f"[Pipeline] ✅ Ses dosyası hazır: {audio_path}")

        # ═══════════════════════════════════════════════════════════════
        # ADIM 2: Transkript (Groq → Gemini fallback)
        # ═══════════════════════════════════════════════════════════════
        update(job_id, "running", "Konuşma metne dönüştürülüyor (Whisper)...", 15)
        transcript_text = ""
        try:
            from transcriber import transcribe, format_transcript_for_gemini
            transcript = transcribe(audio_path)
            if transcript and transcript.get("segments"):
                transcript_text = format_transcript_for_gemini(transcript)
                print(f"[Pipeline] ✅ Transkript hazır: {len(transcript['segments'])} segment")
            else:
                print("[Pipeline] ⚠️ Transkript boş döndü.")
        except Exception as e:
            print(f"[Pipeline] ⚠️ Transkript hatası: {e}")

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
                print(f"[Pipeline] ✅ Enerji analizi hazır")
        except Exception as e:
            print(f"[Pipeline] ⚠️ Enerji analizi hatası: {e}")

        # ═══════════════════════════════════════════════════════════════
        # ADIM 4: RAG + Gemini Analizi
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
        print(f"[Pipeline] ✅ {len(clips_data)} klip doğrulandı.")

        # ═══════════════════════════════════════════════════════════════
        # ADIM 5: Precision Cut
        # ═══════════════════════════════════════════════════════════════
        update(job_id, "running", "Doğal sahne geçişleri saptanıyor ve kesiliyor...", 60)
        clip_paths = cut_clips(local_mp4_path, clips_data, job_id)
        print(f"[Pipeline] ✅ {len(clip_paths)} klip kesildi.")

        # ═══════════════════════════════════════════════════════════════
        # ADIM 6: Rapor Üretimi
        # ═══════════════════════════════════════════════════════════════
        update(job_id, "running", "Raporlar üretiliyor (TXT + PDF)...", 85)
        
        report_data = None
        metadata_path = None
        pdf_path = None
        
        try:
            from report_builder import build_report_data
            report_data = build_report_data(clips_data, transcript)
            print(f"[Pipeline] ✅ Rapor verisi hazırlandı")
        except Exception as e:
            print(f"[Pipeline] ⚠️ report_builder hatası: {e}")
        
        if report_data:
            try:
                from metadata import write_metadata
                metadata_path = write_metadata(report_data, job_id, video_title)
                print(f"[Pipeline] ✅ Metadata TXT: {metadata_path}")
            except Exception as e:
                print(f"[Pipeline] ⚠️ Metadata TXT hatası: {e}")
            
            try:
                from pdf_reporter import write_pdf_report
                pdf_path = write_pdf_report(report_data, job_id, video_title)
                print(f"[Pipeline] ✅ PDF Rapor: {pdf_path}")
            except Exception as e:
                print(f"[Pipeline] ⚠️ PDF rapor hatası: {e}")

        # ═══════════════════════════════════════════════════════════════
        # SONUÇLARI KAYDET (Supabase + Fallback)
        # ═══════════════════════════════════════════════════════════════
        
        result_clips = []
        for i in range(len(clip_paths)):
            report_item = report_data[i] if report_data and i < len(report_data) else None
            clip_result = build_clip_result(
                clip_raw=clips_data[i],
                clip_path=clip_paths[i],
                index=i + 1,
                report_item=report_item,
                transcript=transcript
            )
            result_clips.append(clip_result)
        
        # Klipleri Supabase'e kaydet
        save_clips(job_id, result_clips)
        
        # Job'u tamamla
        update_job(
            job_id,
            status="done",
            step="Modül 1 Tamamlandı",
            progress=100,
            metadata_path=f"/{metadata_path}" if metadata_path else None,
            pdf_path=f"/{pdf_path}" if pdf_path else None,
        )
        
        print(f"[Pipeline] ✅✅✅ İŞLEM TAMAMLANDI — {len(clip_paths)} klip")

    except Exception as e:
        update_job(job_id, status="error", step=f"Hata: {str(e)}", progress=0,
                   error_message=str(e))
        traceback.print_exc()

    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(local_mp4_path):
            os.remove(local_mp4_path)