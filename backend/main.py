"""
main.py (V2.1 - Feedback + Data Flywheel)
-------------------------------------------
Yeni: POST /feedback — klip performans geri bildirimi + otomatik RAG kaydı
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uuid
import os
import shutil
from pathlib import Path

from pipeline import run_pipeline
from database import create_job, get_job, get_user_jobs, delete_job, update_job, submit_clip_feedback, get_client

app = FastAPI()


# --- MODELLER ---
class FeedbackRequest(BaseModel):
    clip_id: int
    job_id: str
    views: Optional[int] = None
    retention: Optional[float] = None  # yüzde (0-100)
    swipe_rate: Optional[float] = None  # yüzde (0-100)


# --- HATA YAKALAYICI ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"!!! 422 HATASI !!!")
    print(f"Hata Detayı: {exc.errors()}")
    print(f"Gelen Body: {exc.body}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "message": "Gönderilen veri backend şablonuna uymuyor!"},
    )

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Klasörler
OUTPUT_DIR = Path("output")
UPLOAD_DIR = Path("temp_uploads")
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

app.mount("/output", StaticFiles(directory="output"), name="output")


# ══════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@app.post("/upload")
async def upload_and_process(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(None)
):
    """Dosyayı alır ve işleme hattını başlatır."""
    job_id = str(uuid.uuid4())
    
    create_job(
        job_id=job_id,
        video_title=title,
        video_description=description or "",
        user_id=None
    )
    
    safe_filename = video.filename.replace(" ", "_").replace("(", "").replace(")", "")
    job_upload_path = UPLOAD_DIR / f"{job_id}_{safe_filename}"
    
    try:
        with open(job_upload_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
        
        print(f"[*] Dosya kaydedildi: {job_upload_path}")
        
        background_tasks.add_task(
            run_pipeline, 
            job_id, 
            str(job_upload_path), 
            title, 
            description if description else ""
        )
        
        return {"job_id": job_id, "message": "Yükleme başarılı, analiz başlatıldı."}

    except Exception as e:
        update_job(job_id, status="error", error_message=f"Sunucuya yazma hatası: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Dosya sunucuya kaydedilemedi."})


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """İş durumunu getirir."""
    job = get_job(job_id)
    if not job:
        return {"error": "İşlem bulunamadı"}
    return job


@app.get("/history")
async def get_history():
    """Geçmiş projeleri getirir."""
    client = get_client()
    if not client:
        return {"jobs": [], "message": "Veritabanı bağlantısı yok"}
    
    try:
        result = (
            client.table("jobs")
            .select("id, video_title, status, progress, created_at, updated_at, metadata_path, pdf_path")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        return {"jobs": result.data if result.data else []}
    except Exception as e:
        print(f"[API] History hatası: {e}")
        return {"jobs": [], "error": str(e)}


@app.get("/history/{job_id}")
async def get_history_detail(job_id: str):
    """Geçmiş projenin detayını getirir."""
    job = get_job(job_id)
    if not job:
        return {"error": "İşlem bulunamadı"}
    return job


@app.delete("/delete/{job_id}")
async def delete_project(job_id: str):
    """Projeyi ve dosyalarını siler."""
    job_dir = OUTPUT_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
        print(f"[API] Disk temizlendi: {job_dir}")
    
    success = delete_job(job_id)
    if success:
        return {"message": "Proje silindi", "job_id": job_id}
    else:
        return JSONResponse(status_code=500, content={"error": "Silme işlemi başarısız"})


@app.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    """
    Klip performans geri bildirimi.
    Feedback skoru 80+ ise otomatik olarak viral_library'ye eklenir (Data Flywheel).
    """
    # 1. Feedback'i clips tablosuna kaydet
    success = submit_clip_feedback(
        clip_id=req.clip_id,
        views=req.views,
        retention=req.retention,
        swipe_rate=req.swipe_rate
    )
    
    if not success:
        return JSONResponse(status_code=500, content={"error": "Feedback kaydedilemedi"})
    
    # 2. Feedback skorunu hesapla
    feedback_score = _calculate_feedback_score(req.views, req.retention, req.swipe_rate)
    
    # 3. Data Flywheel: Skor yeterince yüksekse viral_library'ye ekle
    flywheel_added = False
    if feedback_score >= 80:
        flywheel_added = _add_to_viral_library(req.clip_id, req.job_id, feedback_score)
    
    return {
        "success": True,
        "feedback_score": feedback_score,
        "flywheel_added": flywheel_added,
        "message": "Performans kaydedildi!" + (" RAG kütüphanesi güncellendi." if flywheel_added else "")
    }


def _calculate_feedback_score(views: int = None, retention: float = None, swipe_rate: float = None) -> float:
    """Gerçek dünya metriklerinden feedback skoru hesaplar (0-100)."""
    score = 0.0
    components = 0
    
    if views is not None:
        # 100k+ views = 100 puan, logaritmik ölçek
        import math
        view_score = min(math.log10(max(views, 1)) / 5 * 100, 100)
        score += view_score
        components += 1
    
    if retention is not None:
        # %50+ retention = iyi, %80+ = mükemmel
        retention_score = min(retention / 80 * 100, 100)
        score += retention_score
        components += 1
    
    if swipe_rate is not None:
        # Düşük swipe rate = iyi (tersine çevir)
        # %20 altı = mükemmel, %50+ = kötü
        swipe_score = max(0, 100 - (swipe_rate * 2))
        score += swipe_score
        components += 1
    
    if components == 0:
        return 0.0
    
    return round(score / components, 1)


def _add_to_viral_library(clip_id: int, job_id: str, feedback_score: float) -> bool:
    """
    Data Flywheel: Başarılı klibi viral_library'ye ekler.
    Gelecekte Gemini bu klibi referans alarak daha iyi kesimler yapacak.
    """
    client = get_client()
    if not client:
        return False
    
    try:
        # Klip ve job verilerini çek
        clip_result = client.table("clips").select("*").eq("id", clip_id).execute()
        if not clip_result.data:
            return False
        clip = clip_result.data[0]
        
        job_result = client.table("jobs").select("video_title").eq("id", job_id).execute()
        if not job_result.data:
            return False
        job = job_result.data[0]
        
        # Embedding oluştur
        why_text = f"Hook: {clip.get('hook', '')}. {clip.get('why_selected', '')}. Score: {feedback_score}"
        
        from analyzer import get_embedding
        vector = get_embedding(why_text)
        
        # viral_library'ye ekle
        entry = {
            "video_title": job.get("video_title", ""),
            "hook_text": clip.get("hook", ""),
            "why_it_went_viral": why_text,
            "viral_score": int(feedback_score),
            "source_url": f"clip_pipeline:{job_id}:{clip_id}",
        }
        
        if vector:
            entry["embedding"] = vector
        
        client.table("viral_library").insert(entry).execute()
        print(f"[Flywheel] ✅ Klip #{clip_id} viral_library'ye eklendi (skor: {feedback_score})")
        return True
        
    except Exception as e:
        print(f"[Flywheel] ⚠️ Viral library ekleme hatası: {e}")
        return False


@app.get("/health")
async def health():
    """Sistem sağlık kontrolü."""
    client = get_client()
    db_status = "connected" if client else "fallback (in-memory)"
    return {"ok": True, "database": db_status}