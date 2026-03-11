from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uuid
import os
import shutil
from pathlib import Path
from pipeline import run_pipeline
from state import jobs

app = FastAPI()

# Vercel URL'ni buraya ekleyebilirsin, şimdilik her yerden gelen isteğe açık
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Çıktı ve geçici yükleme klasörlerini ayarla
OUTPUT_DIR = Path("output")
UPLOAD_DIR = Path("temp_uploads")
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

app.mount("/output", StaticFiles(directory="output"), name="output")

@app.post("/upload")
async def upload_and_process(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(...)
):
    """
    Vercel'den gelen MP4 dosyasını, başlığı ve açıklamayı kabul eder.
    """
    job_id = str(uuid.uuid4())
    
    # 1. Kayıt Başlatılıyor
    jobs[job_id] = {
        "status": "uploading", 
        "step": "Dosya sunucuya yazılıyor...", 
        "progress": 5, 
        "result": None, 
        "error": None
    }
    
    # 2. Dosyayı Railway diskine güvenli bir şekilde kaydet
    job_upload_path = UPLOAD_DIR / f"{job_id}_{video.filename}"
    try:
        with open(job_upload_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = f"Yükleme hatası: {str(e)}"
        return {"error": "Dosya kaydedilemedi"}

    # 3. Şefi (Pipeline) göreve çağır
    # Video yolunu, manuel başlığı ve açıklamayı gönderiyoruz
    background_tasks.add_task(
        run_pipeline, 
        job_id, 
        str(job_upload_path), 
        title, 
        description
    )
    
    return {"job_id": job_id, "message": "Yükleme başarılı, analiz başlıyor."}

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        return {"error": "İşlem bulunamadı"}
    return jobs[job_id]

@app.get("/health")
async def health():
    return {"ok": True, "storage": "ready"}