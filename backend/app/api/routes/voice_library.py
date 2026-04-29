"""
Voice Library — reference voice fingerprints for speaker identification.

Allows users to upload a clean audio sample of a person (guest/host), which
is sent to Modal to compute a WeSpeaker ResNet293 embedding (256-dim).
The embedding + R2 audio URL is stored in person_voices.

Used downstream by the (future) speaker-ID step to match Deepgram clusters
in an episode against a known person's voice.
"""

from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks

from app.middleware.auth import get_current_user
from app.services.supabase_client import get_client
from app.config import settings

router = APIRouter(prefix="/voice-library", tags=["voice-library"])

_ALLOWED_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm", ".mp4"}
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB — generous; typical clean sample <1 MB


def _safe_audio_ext(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in _ALLOWED_AUDIO_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio extension. Allowed: {sorted(_ALLOWED_AUDIO_EXTS)}",
        )
    return ext


def _upload_audio_to_r2(audio_bytes: bytes, filename: str) -> str:
    """Upload audio sample to R2 under voice-library/ prefix. Returns public URL."""
    from app.services.r2_client import get_r2_client

    s3 = get_r2_client()
    bucket = settings.R2_BUCKET_NAME
    if not bucket:
        raise RuntimeError("R2_BUCKET_NAME not set")

    key = f"voice-library/{filename}"
    content_type = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".mp4": "audio/mp4",
    }.get(os.path.splitext(filename)[1].lower(), "application/octet-stream")

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=audio_bytes,
        ContentType=content_type,
    )

    public_url = (settings.R2_PUBLIC_URL or "").rstrip("/")
    if not public_url:
        raise RuntimeError("R2_PUBLIC_URL not set")
    return f"{public_url}/{key}"


def _compute_embedding_via_modal(audio_bytes: bytes, filename: str) -> dict:
    """
    Call the Modal `compute_voice_embedding` function. Returns dict with
    `embedding` (list[float], 256-dim) and `duration_sec`, or raises on error.
    """
    try:
        import modal
    except ImportError:
        raise RuntimeError("modal package not installed in backend")

    try:
        fn = modal.Function.from_name("gpu-pipeline", "compute_voice_embedding")
    except Exception as e:
        raise RuntimeError(f"Modal function not deployed: {e}")

    result = fn.remote(audio_bytes, filename)
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected Modal response: {type(result)}")
    if "error" in result:
        raise RuntimeError(f"Modal embedding failed: {result['error']}")
    if "embedding" not in result or not isinstance(result["embedding"], list):
        raise RuntimeError("Modal response missing embedding")
    return result


@router.get("")
async def list_voices(current_user: dict = Depends(get_current_user)):
    """List all voice fingerprints. Shared library, not per-user."""
    try:
        sb = get_client()
        result = (
            sb.table("person_voices")
            .select("id,name,sample_duration_sec,audio_path,created_at,updated_at")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        print(f"[VoiceLibrary] list error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list voices")


@router.post("")
async def create_voice(
    name: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload an audio sample for a person and compute their voice fingerprint.
    Name must be unique. Runs Modal embedding synchronously (~5-10s).
    """
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if len(name) > 120:
        raise HTTPException(status_code=400, detail="Name too long (max 120 chars)")

    ext = _safe_audio_ext(file.filename or "")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")
    if len(audio_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )

    sb = get_client()

    # Uniqueness check
    existing = sb.table("person_voices").select("id").eq("name", name).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail=f"Voice '{name}' already exists")

    # Upload to R2 first (cheap & fast — if embedding fails, user can retry)
    safe_name = f"{uuid.uuid4().hex}{ext}"
    try:
        audio_url = _upload_audio_to_r2(audio_bytes, safe_name)
    except Exception as e:
        print(f"[VoiceLibrary] R2 upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Audio upload failed: {e}")

    # Compute embedding via Modal
    try:
        emb_result = _compute_embedding_via_modal(audio_bytes, safe_name)
    except Exception as e:
        print(f"[VoiceLibrary] embedding failed: {e}")
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

    embedding = emb_result["embedding"]
    duration = float(emb_result.get("duration_sec") or 0.0)

    if len(embedding) != 192:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected embedding dim: {len(embedding)} (expected 192)",
        )

    # Insert
    try:
        insert = (
            sb.table("person_voices")
            .insert(
                {
                    "name": name,
                    "embedding": embedding,
                    "sample_duration_sec": duration,
                    "audio_path": audio_url,
                }
            )
            .execute()
        )
    except Exception as e:
        print(f"[VoiceLibrary] DB insert failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database insert failed: {e}")

    row = (insert.data or [{}])[0]
    return {
        "id": row.get("id"),
        "name": name,
        "sample_duration_sec": duration,
        "audio_path": audio_url,
        "created_at": row.get("created_at"),
    }


@router.delete("/{voice_id}")
async def delete_voice(voice_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a voice fingerprint by ID. Also removes the R2 audio file."""
    try:
        sb = get_client()

        existing = (
            sb.table("person_voices")
            .select("id,name,audio_path")
            .eq("id", voice_id)
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Voice not found")

        audio_path = (existing.data[0] or {}).get("audio_path")

        sb.table("person_voices").delete().eq("id", voice_id).execute()

        # Best-effort R2 cleanup
        if audio_path:
            try:
                from app.services.r2_client import get_r2_client
                public_url = (settings.R2_PUBLIC_URL or "").rstrip("/")
                if public_url and audio_path.startswith(public_url):
                    key = audio_path[len(public_url) + 1:]
                    s3 = get_r2_client()
                    s3.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
            except Exception as e:
                print(f"[VoiceLibrary] R2 delete warning (non-fatal): {e}")

        return {"deleted": True, "id": voice_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[VoiceLibrary] delete error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete voice")
