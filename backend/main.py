"""
main.py (V2.0 - Supabase Integrated)
--------------------------------------
FastAPI endpoints + Supabase entegrasyonu.
Yeni endpoint'ler: /history, /delete/{job_id}
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import uuid
import os
import shutil
from pathlib import Path

from pipeline import run_pipeline
from database import create_job, get_job, get_user_jobs, delete_job, update_job

app = FastAPI()

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
    
    # Job'u Supabase'e kaydet (veya in-memory fallback)
    create_job(
        job_id=job_id,
        video_title=title,
        video_description=description or "",
        user_id=None  # Auth eklenince buraya user_id gelecek
    )
    
    # Dosyayı kaydet
    safe_filename = video.filename.replace(" ", "_").replace("(", "").replace(")", "")
    job_upload_path = UPLOAD_DIR / f"{job_id}_{safe_filename}"
    
    try:
        with open(job_upload_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
        
        print(f"[*] Dosya kaydedildi: {job_upload_path}")
        
        # Pipeline'ı arka planda başlat
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
    """İş durumunu getirir (Supabase veya in-memory fallback)."""
    job = get_job(job_id)
    if not job:
        return {"error": "İşlem bulunamadı"}
    return job


@app.get("/history")
async def get_history():
    """
    Kullanıcının geçmiş projelerini getirir.
    Auth eklenince user_id filtrelenecek.
    Şimdilik tüm job'ları döndürür (tek kullanıcılı sistem).
    """
    # Auth yokken: Supabase'den son 20 job'u çek
    from database import get_client
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
    """Geçmiş bir projenin detayını (klipleriyle birlikte) getirir."""
    job = get_job(job_id)
    if not job:
        return {"error": "İşlem bulunamadı"}
    return job


@app.delete("/delete/{job_id}")
async def delete_project(job_id: str):
    """
    Projeyi ve ilişkili dosyaları siler.
    - Supabase'den job + clips (CASCADE)
    - Diskten output/{job_id}/ klasörü
    """
    # Disk temizliği
    job_dir = OUTPUT_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
        print(f"[API] 🧹 Disk temizlendi: {job_dir}")
    
    # DB temizliği
    success = delete_job(job_id)
    
    if success:
        return {"message": "Proje silindi", "job_id": job_id}
    else:
        return JSONResponse(status_code=500, content={"error": "Silme işlemi başarısız"})


@app.get("/health")
async def health():
    """Sistem sağlık kontrolü."""
    from database import get_client
    db_status = "connected" if get_client() else "fallback (in-memory)"
    return {"ok": True, "database": db_status}