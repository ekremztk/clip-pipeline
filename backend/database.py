"""
database.py (V2.0 - Supabase Integration)
------------------------------------------
state.py'nin yerini alan kalıcı veritabanı modülü.
Supabase (PostgreSQL) üzerinde jobs ve clips tablolarını yönetir.

Backend service_role key ile çalışır → RLS bypass edilir.
Bu sayede auth olmadan pipeline yazma işlemi yapılabilir.

Geriye dönük uyumluluk: Supabase bağlantısı başarısız olursa
in-memory fallback devreye girer (state.py davranışı).
"""

import os
import json
from datetime import datetime
from typing import Optional

# Supabase client
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None  # type: ignore
    print("[Database] ⚠️ supabase-py kurulu değil. pip install supabase")

# --- BAĞLANTI ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # service_role key (RLS bypass)

_client: Optional[Client] = None
_fallback_jobs: dict = {}  # In-memory fallback


def get_client() -> Optional[Client]:
    """Supabase client'ı lazy-init ile döndürür."""
    global _client
    
    if _client is not None:
        return _client
    
    if not SUPABASE_AVAILABLE:
        print("[Database] ⚠️ supabase-py yok, in-memory fallback aktif.")
        return None
    
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("[Database] ⚠️ SUPABASE_URL veya SUPABASE_SERVICE_KEY tanımlı değil.")
        print("[Database] In-memory fallback aktif.")
        return None
    
    try:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("[Database] ✅ Supabase bağlantısı kuruldu.")
        return _client
    except Exception as e:
        print(f"[Database] ❌ Supabase bağlantı hatası: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════
# JOBS CRUD
# ══════════════════════════════════════════════════════════════════════

def create_job(job_id: str, video_title: str, video_description: str = "",
               user_id: str = None, channel_id: str = "speedy_cast") -> dict:
    """Yeni iş kaydı oluşturur."""
    job_data = {
        "id": job_id,
        "video_title": video_title,
        "video_description": video_description or "",
        "status": "uploading",
        "step": "Dosya sunucuya yazılıyor...",
        "progress": 5,
        "channel_id": channel_id,
    }
    
    if user_id:
        job_data["user_id"] = user_id
    
    client = get_client()
    if client:
        try:
            client.table("jobs").insert(job_data).execute()
            print(f"[Database] ✅ Job oluşturuldu (Supabase): {job_id}")
        except Exception as e:
            print(f"[Database] ⚠️ Job insert hatası: {e}")
            _fallback_jobs[job_id] = {**job_data, "result": None, "error": None}
    else:
        _fallback_jobs[job_id] = {**job_data, "result": None, "error": None}
    
    return job_data


def update_job(job_id: str, status: str = None, step: str = None, 
               progress: int = None, error_message: str = None,
               metadata_path: str = None, pdf_path: str = None):
    """İş durumunu günceller."""
    updates = {}
    if status is not None:
        updates["status"] = status
    if step is not None:
        updates["step"] = step
    if progress is not None:
        updates["progress"] = progress
    if error_message is not None:
        updates["error_message"] = error_message
    if metadata_path is not None:
        updates["metadata_path"] = metadata_path
    if pdf_path is not None:
        updates["pdf_path"] = pdf_path
    
    if not updates:
        return
    
    client = get_client()
    if client:
        try:
            client.table("jobs").update(updates).eq("id", job_id).execute()
        except Exception as e:
            print(f"[Database] ⚠️ Job update hatası: {e}")
            # Fallback'e de yaz
            if job_id in _fallback_jobs:
                _fallback_jobs[job_id].update(updates)
    else:
        if job_id in _fallback_jobs:
            _fallback_jobs[job_id].update(updates)


def get_job(job_id: str) -> Optional[dict]:
    """İş durumunu getirir."""
    client = get_client()
    if client:
        try:
            result = client.table("jobs").select("*").eq("id", job_id).execute()
            if result.data:
                job = result.data[0]
                # Klipleri de çek
                clips_result = client.table("clips").select("*").eq("job_id", job_id).order("clip_index").execute()
                
                # Frontend'in beklediği formata dönüştür
                return _format_job_for_frontend(job, clips_result.data if clips_result.data else [])
        except Exception as e:
            print(f"[Database] ⚠️ Job get hatası: {e}")
    
    # Fallback
    if job_id in _fallback_jobs:
        return _fallback_jobs[job_id]
    
    return None


def save_clips(job_id: str, clips: list[dict], channel_id: str = "speedy_cast"):
    """Klip sonuçlarını veritabanına kaydeder."""
    client = get_client()
    if not client:
        # Fallback: in-memory'de result olarak sakla
        if job_id in _fallback_jobs:
            _fallback_jobs[job_id]["result"] = {"clips": clips}
        return
    
    rows = []
    for clip in clips:
        rows.append({
            "job_id": job_id,
            "clip_index": clip.get("index", 0),
            "hook": clip.get("hook", ""),
            "score": clip.get("score", 0),
            "path": clip.get("path", ""),
            "psychological_trigger": clip.get("psychological_trigger", ""),
            "rag_reference_used": clip.get("rag_reference_used", ""),
            "why_selected": clip.get("why_selected", ""),
            "suggested_title": clip.get("suggested_title", ""),
            "suggested_description": clip.get("suggested_description", ""),
            "suggested_hashtags": clip.get("suggested_hashtags", ""),
            "transcript_excerpt": clip.get("transcript_excerpt", ""),
            "audio_energy_note": clip.get("audio_energy_note", ""),
            "trim_note": clip.get("trim_note", ""),
            "channel_id": channel_id,
        })
    
    try:
        client.table("clips").insert(rows).execute()
        print(f"[Database] ✅ {len(rows)} klip kaydedildi (Supabase): {job_id}")
    except Exception as e:
        print(f"[Database] ⚠️ Clips insert hatası: {e}")
        # Fallback
        if job_id in _fallback_jobs:
            _fallback_jobs[job_id]["result"] = {"clips": clips}


def get_user_jobs(user_id: str = None, channel_id: str = "speedy_cast", limit: int = 20) -> list[dict]:
    """Kullanıcının tüm job'larını getirir (geçmiş projeler)."""
    client = get_client()
    if not client:
        return []
    
    try:
        query = (
            client.table("jobs")
            .select("id, video_title, status, progress, created_at, updated_at, metadata_path, pdf_path")
            .eq("channel_id", channel_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if user_id:
            query = query.eq("user_id", user_id)
        result = query.execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"[Database] ⚠️ User jobs hatası: {e}")
        return []


def delete_job(job_id: str, user_id: str = None) -> bool:
    """Job ve ilişkili klipleri siler (CASCADE)."""
    client = get_client()
    if not client:
        if job_id in _fallback_jobs:
            del _fallback_jobs[job_id]
        return True
    
    try:
        query = client.table("jobs").delete().eq("id", job_id)
        if user_id:
            query = query.eq("user_id", user_id)
        query.execute()
        print(f"[Database] ✅ Job silindi: {job_id}")
        return True
    except Exception as e:
        print(f"[Database] ⚠️ Job delete hatası: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════
# DATA FLYWHEEL (Gelecek kullanım)
# ══════════════════════════════════════════════════════════════════════

def submit_clip_feedback(clip_id: int, views: int = None, retention: float = None,
                         swipe_rate: float = None) -> bool:
    """Klip performans geri bildirimi kaydeder."""
    client = get_client()
    if not client:
        return False
    
    updates = {"feedback_submitted_at": datetime.utcnow().isoformat()}
    if views is not None:
        updates["real_views"] = views
    if retention is not None:
        updates["real_retention"] = retention
    if swipe_rate is not None:
        updates["real_swipe_rate"] = swipe_rate
    
    # Basit feedback skoru hesapla
    if views and retention:
        # Normalize: 100k+ views = max, 50%+ retention = max
        view_score = min(views / 100000, 1.0) * 50
        retention_score = min(retention / 50, 1.0) * 50
        updates["feedback_score"] = round(view_score + retention_score, 1)
    
    try:
        client.table("clips").update(updates).eq("id", clip_id).execute()
        return True
    except Exception as e:
        print(f"[Database] ⚠️ Feedback hatası: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ══════════════════════════════════════════════════════════════════════

def _format_job_for_frontend(job: dict, clips_db: list) -> dict:
    """
    Supabase job + clips verisini frontend'in beklediği formata dönüştürür.
    Bu format mevcut /status/{job_id} endpoint'iyle uyumludur.
    """
    formatted_clips = []
    for c in clips_db:
        formatted_clips.append({
            "index": c.get("clip_index", 0),
            "hook": c.get("hook", ""),
            "score": c.get("score", 0),
            "path": c.get("path", ""),
            "psychological_trigger": c.get("psychological_trigger", ""),
            "rag_reference_used": c.get("rag_reference_used", ""),
            "why_selected": c.get("why_selected", ""),
            "suggested_title": c.get("suggested_title", ""),
            "suggested_description": c.get("suggested_description", ""),
            "suggested_hashtags": c.get("suggested_hashtags", ""),
            "transcript_excerpt": c.get("transcript_excerpt", ""),
        })
    
    result = None
    if job.get("status") == "done" and formatted_clips:
        result = {
            "original_title": job.get("video_title", ""),
            "clips_count": len(formatted_clips),
            "clips": formatted_clips,
            "metadata_path": job.get("metadata_path"),
            "pdf_path": job.get("pdf_path"),
        }
    
    return {
        "status": job.get("status", "error"),
        "step": job.get("step", ""),
        "progress": job.get("progress", 0),
        "result": result,
        "error": job.get("error_message"),
    }