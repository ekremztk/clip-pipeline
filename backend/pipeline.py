"""
pipeline.py (V3.2 - Subprocess & Security Update)
"""

import os
import subprocess # os.system yerine bunu ekledik
import traceback
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
    try:
        # --- ADIM 1: Audio Extraction (Güvenli Yöntem) ---
        update(job_id, "running", "Ses verisi ayıklanıyor...", 10)
        
        # os.system yerine subprocess.run kullanarak dosya adındaki 
        # parantezlerin ( ) sistemi çökertmesini engelliyoruz.
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

        # --- ADIM 2: RAG & Gemini Analizi ---
        update(job_id, "running", "RAG & Gemini Viral Analizi yapılıyor...", 30)
        full_context = f"Title: {video_title}\nDescription: {video_description}"
        
        clips_data = analyze_video_for_clips(audio_path, full_context)

        if not clips_data:
            raise RuntimeError("Yapay zeka bu videoda kriterlere uygun viral klip bulamadı.")

        # --- ADIM 3: PySceneDetect & Lossless Cut ---
        update(job_id, "running", "Doğal sahne geçişleri saptanıyor ve kesiliyor...", 60)
        clip_paths = cut_clips(local_mp4_path, clips_data, job_id)

        # --- SONUÇLARI HAZIRLA ---
        jobs[job_id]["status"] = "done"
        jobs[job_id]["step"] = "Modül 1 Tamamlandı"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["result"] = {
            "original_title": video_title,
            "clips_count": len(clip_paths),
            "clips": [
                {
                    "index": i + 1,
                    "hook": clips_data[i].get("hook_text"),
                    "score": clips_data[i].get("virality_score"),
                    # Yeni eklenen iki satır:
                    "psychological_trigger": clips_data[i].get("psychological_trigger"),
                    "rag_reference_used": clips_data[i].get("rag_reference_used"),
                    
                    "path": f"/{clip_paths[i]}" 
                } for i in range(len(clip_paths))
            ]
        }

    except Exception as e:
        update(job_id, "error", f"Hata: {str(e)}", 0)
        traceback.print_exc()

    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(local_mp4_path):
            os.remove(local_mp4_path)