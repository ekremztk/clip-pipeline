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
from state import jobs

app = FastAPI()

# --- HATA YAKALAYICI (DEBUG MODE) ---
# Bu kısım, 422 hatası aldığımızda loglara hatanın nedenini (hangi alanın eksik olduğunu) yazar.
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"!!! 422 HATASI TESPİT EDİLDİ !!!")
    print(f"Hata Detayı: {exc.errors()}")
    print(f"Gelen Body: {exc.body}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "message": "Gönderilen veri backend şablonuna uymuyor!"},
    )

# CORS Ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Klasör Hazırlığı
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
    description: str = Form(None) # 'none' yerine 'None' (Büyük harf şart)
):
    """
    Frontend'den gelen dosyayı alır ve işleme hattını başlatır.
    """
    job_id = str(uuid.uuid4())
    
    # İş Başlatılıyor
    jobs[job_id] = {
        "status": "uploading", 
        "step": "Dosya Railway sunucusuna yazılıyor...", 
        "progress": 5, 
        "result": None, 
        "error": None
    }
    
    # Dosya Adını Temizle ve Kaydet
    # (Boşlukları ve garip karakterleri temizlemek dosya sistemi için daha güvenlidir)
    safe_filename = video.filename.replace(" ", "_").replace("(", "").replace(")", "")
    job_upload_path = UPLOAD_DIR / f"{job_id}_{safe_filename}"
    
    try:
        with open(job_upload_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
        
        print(f"[*] Dosya başarıyla kaydedildi: {job_upload_path}")
        
        # Pipeline'ı Arka Planda Başlat
        background_tasks.add_task(
            run_pipeline, 
            job_id, 
            str(job_upload_path), 
            title, 
            description if description else ""
        )
        
        return {"job_id": job_id, "message": "Yükleme başarılı, analiz arka planda başlatıldı."}

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = f"Sunucuya yazma hatası: {str(e)}"
        return JSONResponse(status_code=500, content={"error": "Dosya sunucuya kaydedilemedi."})

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        return {"error": "İşlem bulunamadı"}
    return jobs[job_id]

@app.get("/health")
async def health():
    return {"ok": True, "storage": "ready"}