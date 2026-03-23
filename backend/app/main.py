from dotenv import load_dotenv

# Load .env variables at the top
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create directories on startup if they don't exist
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield

from app.api.routes import jobs, clips, speakers, downloads, channels, feedback, captions, proxy, youtube_metadata, reframe
from app.api.websocket import progress

app = FastAPI(
    title="Prognot Clip Pipeline",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure OUTPUT_DIR exists before mounting to prevent StaticFiles from throwing RuntimeError
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(settings.OUTPUT_DIR)), name="output")

app.include_router(jobs.router)
app.include_router(clips.router)
app.include_router(speakers.router)
app.include_router(downloads.router)
app.include_router(channels.router)
app.include_router(feedback.router)
app.include_router(captions.router)
app.include_router(proxy.router)
app.include_router(youtube_metadata.router)
app.include_router(reframe.router)
app.include_router(progress.router)

from editor_main import editor_router
app.include_router(editor_router)

@app.get("/health")
async def health_check():
    return {
        "ok": True,
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT
    }
