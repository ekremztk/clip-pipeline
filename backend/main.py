from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uuid
import os
from pathlib import Path
from pipeline import run_pipeline
from state import jobs

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
app.mount("/output", StaticFiles(directory="output"), name="output")

class ProcessRequest(BaseModel):
    url: str
    clip_count: int = 0  # 0 = auto (AI decides)

@app.post("/process")
async def process_video(req: ProcessRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "step": "", "progress": 0, "result": None, "error": None}
    background_tasks.add_task(run_pipeline, job_id, req.url, req.clip_count)
    return {"job_id": job_id}

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        return {"error": "Job not found"}
    return jobs[job_id]

@app.get("/health")
async def health():
    return {"ok": True}