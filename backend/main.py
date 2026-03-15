"""
main.py (V2.1 - Feedback + Data Flywheel)
-------------------------------------------
Yeni: POST /feedback — klip performans geri bildirimi + otomatik RAG kaydı
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, Request, HTTPException
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
from database import create_job, get_job, get_user_jobs, update_job, submit_clip_feedback, get_client

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
    description: str = Form(None),
    channel_id: str = Form(default="speedy_cast")
):
    """Dosyayı alır ve işleme hattını başlatır."""
    job_id = str(uuid.uuid4())
    
    create_job(
        job_id=job_id,
        video_title=title,
        video_description=description or "",
        user_id=None,
        channel_id=channel_id
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
            description if description else "",
            channel_id
        )
        
        return {"job_id": job_id, "message": "Yükleme başarılı, analiz başlatıldı."}

    except Exception as e:
        update_job(job_id, status="error", error_message=f"Sunucuya yazma hatası: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Dosya sunucuya kaydedilemedi."})


@app.get("/jobs")
async def get_jobs(channel_id: str = "speedy_cast"):
    """Kanala ait geçmiş işleri getirir."""
    return get_user_jobs(channel_id=channel_id)


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


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    try:
        # 1. & 2. Supabase silme işlemleri
        client = get_client()
        if client:
            client.table("clips").delete().eq("job_id", job_id).execute()
            client.table("jobs").delete().eq("id", job_id).execute()
            
        # 3. state.py in-memory store'dan silme
        try:
            import state
            if hasattr(state, "jobs"):
                state.jobs.pop(job_id, None)
        except ImportError:
            pass
            
        # 4. output/{job_id}/ klasörünü silme
        job_dir = OUTPUT_DIR / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)
            print(f"[API] Disk temizlendi: {job_dir}")
            
        # 5. Başarı dönüşü
        return {"deleted": True, "job_id": job_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
@app.get("/test_deploy_v2")
async def test_deploy():
    return {"deployed": True, "version": "v2_with_jobs"}

# =============================================
# V3.1 INTELLIGENCE ENGINE ENDPOINTS
# =============================================

# --- Pydantic Models ---
class FeedbackV2Request(BaseModel):
    clip_id: int
    job_id: str
    views: Optional[int] = None
    views_48h: Optional[int] = None
    views_7d: Optional[int] = None
    retention: Optional[float] = None
    avg_watch_pct: Optional[float] = None
    first_3s_retention: Optional[float] = None
    swipe_rate: Optional[float] = None

# --- Genome ---
@app.get("/v2/genome/{channel_id}")
async def get_genome_endpoint(channel_id: str):
    try:
        from genome import get_genome
        data = get_genome(channel_id)
        if not data:
            return {"error": "Genome not found", "channel_id": channel_id}
        return data
    except Exception as e:
        return {"error": str(e)}

@app.post("/v2/genome/{channel_id}/recalculate")
async def recalculate_genome(channel_id: str):
    try:
        from genome import calculate_genome, save_genome
        data = calculate_genome(channel_id)
        if data:
            save_genome(channel_id, data)
        return {"success": bool(data), "genome": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/v2/genome/{channel_id}/rollback/{version_id}")
async def rollback_genome(channel_id: str, version_id: int):
    try:
        from genome import rollback_genome as rb
        result = rb(channel_id, version_id)
        return {"success": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Feedback V2 ---
@app.post("/v2/feedback/{clip_id}")
async def submit_feedback_v2(clip_id: int, req: FeedbackV2Request):
    try:
        from feedback import process_feedback
        result = process_feedback(
            clip_id=clip_id,
            views=req.views,
            retention=req.retention,
            swipe_rate=req.swipe_rate,
            views_48h=req.views_48h,
            views_7d=req.views_7d
        )
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/v2/feedback/bulk-import")
async def bulk_import_feedback():
    # TODO: CSV/JSON import
    return {"message": "Not implemented yet"}

# --- Correlation ---
@app.get("/v2/correlation/{channel_id}")
async def get_correlation(channel_id: str):
    try:
        from correlation import get_correlation_rules
        rules = get_correlation_rules(channel_id)
        return {"channel_id": channel_id, "rules": rules or []}
    except Exception as e:
        return {"error": str(e)}

# --- Health ---
@app.get("/v2/health/{channel_id}")
async def get_health(channel_id: str):
    try:
        from health import generate_health_report
        report = generate_health_report(channel_id)
        return report or {"status": "unknown", "error": "No data"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# --- Celebrity Registry ---
@app.get("/v2/celebrity-registry")
async def get_celebrities():
    try:
        from database import get_celebrities
        return {"celebrities": get_celebrities() or []}
    except Exception as e:
        return {"error": str(e)}

@app.post("/v2/celebrity-registry")
async def add_celebrity(name: str, tier: str = "unknown"):
    try:
        from database import upsert_celebrity
        result = upsert_celebrity(name=name, tier=tier)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
