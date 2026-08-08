from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException, Depends, Request, Body
from pydantic import BaseModel
from app.services.supabase_client import get_client
from app.middleware.auth import get_current_user
from app.services import storage
from app.pipeline.orchestrator import run_pipeline
from app.models.schemas import JobResponse
from app.models.enums import JobStatus
from app.config import settings
from app.limiter import limiter
import uuid
import shutil
import os
import json
import subprocess

# Allowed video MIME types and extensions
_ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska", "video/webm"}
_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

router = APIRouter(prefix="/jobs", tags=["jobs"])

def get_video_duration(file_path: str) -> float:
    try:
        cmd = [
            "ffprobe", 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ffprobe] Error getting duration: {e}")
        return 0.0

@router.post("/upload-preview")
@limiter.limit("10/minute")
async def upload_preview(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Instantly uploads a video file and returns its duration.
    Called as soon as user selects a file, before job creation.
    Rate limited: 10 uploads/minute per IP.
    """
    try:
        # YÜKS-3: Validate MIME type
        if file.content_type not in _ALLOWED_VIDEO_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported file format")

        # YÜKS-3: Sanitize filename — use only UUID + safe extension, ignore user-provided name
        original_ext = os.path.splitext(file.filename or "")[1].lower()
        if original_ext not in _ALLOWED_VIDEO_EXTS:
            original_ext = ".mp4"
        upload_id = str(uuid.uuid4())
        safe_filename = f"{upload_id}{original_ext}"
        file_path = settings.UPLOAD_DIR / safe_filename

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        ffprobe_cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "json", str(file_path)
        ]
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        duration_seconds = float(data["format"]["duration"])

        print(f"[UploadPreview] Uploaded {safe_filename}, duration: {duration_seconds:.1f}s")

        # YÜKS-2: Never return server file_path to client
        return {
            "upload_id": upload_id,
            "duration_seconds": duration_seconds,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[UploadPreview] Error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")


class PresignUploadBody(BaseModel):
    filename: str
    content_type: str
    size_bytes: int


class RegisterUploadBody(BaseModel):
    upload_id: str
    # Optional: if frontend couldn't read metadata (big files, moov at end),
    # backend will measure it by downloading the R2 head and running ffprobe.
    duration_seconds: Optional[float] = None


class MpuInitBody(BaseModel):
    filename: str
    content_type: str
    size_bytes: int


class MpuSignPartBody(BaseModel):
    upload_id: str
    part_number: int


class MpuCompletePart(BaseModel):
    part_number: int
    etag: str


class MpuCompleteBody(BaseModel):
    upload_id: str
    parts: list[MpuCompletePart]


class MpuAbortBody(BaseModel):
    upload_id: str


@router.post("/presign-upload")
@limiter.limit("20/hour")
async def presign_upload(
    request: Request,
    body: PresignUploadBody,
    current_user: dict = Depends(get_current_user),
):
    """
    Return a presigned R2 PUT URL so the browser uploads directly, bypassing Railway.
    Creates a `video_uploads` row; frontend calls /register-upload once the PUT completes.
    """
    if body.content_type not in _ALLOWED_VIDEO_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file format")
    if body.size_bytes <= 0:
        raise HTTPException(status_code=400, detail="size_bytes must be > 0")
    if body.size_bytes > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {settings.MAX_UPLOAD_BYTES // (1024 * 1024 * 1024)} GB)",
        )

    ext = os.path.splitext(body.filename or "")[1].lower()
    if ext not in _ALLOWED_VIDEO_EXTS:
        ext = ".mp4"

    upload_id = str(uuid.uuid4())
    r2_key = f"upload_sources/{current_user['id']}/{upload_id}{ext}"

    try:
        from app.services.r2_client import generate_presigned_put
        upload_url = generate_presigned_put(r2_key, body.content_type, expires_in=3600)
    except Exception as e:
        print(f"[PresignUpload] R2 presign error: {e}")
        raise HTTPException(status_code=500, detail="Could not create upload URL")

    try:
        supabase = get_client()
        supabase.table("video_uploads").insert({
            "id": upload_id,
            "user_id": current_user["id"],
            "r2_key": r2_key,
            "filename": body.filename,
            "content_type": body.content_type,
            "size_bytes": body.size_bytes,
        }).execute()
    except Exception as e:
        print(f"[PresignUpload] DB insert error: {e}")
        raise HTTPException(status_code=500, detail="Could not register upload")

    print(f"[PresignUpload] user={current_user['id']} id={upload_id} size={body.size_bytes}")
    return {"upload_id": upload_id, "upload_url": upload_url, "r2_key": r2_key}


def _probe_duration_from_url(url: str) -> float:
    """
    Run ffprobe over an HTTP(S) URL so we don't have to download the full
    object — ffprobe will range-request only the moov atom.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        url,
    ]
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, check=True, timeout=120,
    )
    return float(result.stdout.strip())


@router.post("/register-upload")
@limiter.limit("40/hour")
async def register_upload(
    request: Request,
    body: RegisterUploadBody,
    current_user: dict = Depends(get_current_user),
):
    """
    Called by the browser right after the presigned PUT finishes. The frontend
    tries to read duration via `<video>.onloadedmetadata`, but big files with
    a trailing `moov` atom often fail. If duration_seconds is missing/zero,
    fall back to server-side ffprobe over a short-lived presigned GET URL.
    """
    try:
        supabase = get_client()

        # Look up the row so we know the R2 key (needed for ffprobe fallback).
        lookup = (
            supabase.table("video_uploads")
            .select("id, r2_key")
            .eq("id", body.upload_id)
            .eq("user_id", current_user["id"])
            .single()
            .execute()
        )
        if not lookup.data:
            raise HTTPException(status_code=404, detail="Upload not found")
        r2_key = lookup.data["r2_key"]

        duration = body.duration_seconds or 0.0
        if duration <= 0:
            # Browser couldn't read metadata; measure server-side.
            try:
                from app.services.r2_client import generate_presigned_get, object_exists
                if not object_exists(r2_key):
                    raise HTTPException(
                        status_code=409,
                        detail="Upload not found in storage — PUT may not have completed.",
                    )
                signed_get = generate_presigned_get(r2_key, expires_in=600)
                duration = _probe_duration_from_url(signed_get)
                print(f"[RegisterUpload] ffprobe fallback id={body.upload_id} duration={duration:.1f}s")
            except HTTPException:
                raise
            except Exception as e:
                print(f"[RegisterUpload] ffprobe fallback failed: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="Could not read video duration. File may be corrupt.",
                )

        upd = (
            supabase.table("video_uploads")
            .update({"duration_seconds": duration, "ready": True})
            .eq("id", body.upload_id)
            .eq("user_id", current_user["id"])
            .execute()
        )
        if not upd.data:
            raise HTTPException(status_code=404, detail="Upload not found")
        print(f"[RegisterUpload] id={body.upload_id} duration={duration:.1f}s ready=True")
        return {"ok": True, "upload_id": body.upload_id, "duration_seconds": duration}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RegisterUpload] error: {e}")
        raise HTTPException(status_code=500, detail="Failed to register upload")


# --- Multipart upload (parallel parts) ---------------------------------------
# Single PUT of multi-GB files saturates a single TCP connection at ~40% of the
# link's capacity. S3-compatible multipart upload splits the object into parts
# that the browser uploads in parallel, typically 2–4× faster on the same link.
# R2 supports this 1:1 with the S3 API.

# R2 requires parts to be 5 MiB–5 GiB and at most 10,000 per upload.
_MPU_MIN_PART_SIZE = 5 * 1024 * 1024            # 5 MiB (R2 minimum)
_MPU_MAX_PARTS = 10_000
_MPU_PART_URL_TTL = 6 * 3600                    # 6h per-part URL


@router.post("/mpu/init")
@limiter.limit("20/hour")
async def mpu_init(
    request: Request,
    body: MpuInitBody,
    current_user: dict = Depends(get_current_user),
):
    """
    Start a multipart upload. Returns `upload_id` (our DB id) and the R2 `mpu_upload_id`
    needed when signing parts / completing. The frontend decides its own part size and
    count; we only enforce R2's 5 MiB / 10,000-part limits at sign + complete time.
    """
    if body.content_type not in _ALLOWED_VIDEO_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file format")
    if body.size_bytes <= 0:
        raise HTTPException(status_code=400, detail="size_bytes must be > 0")
    if body.size_bytes > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {settings.MAX_UPLOAD_BYTES // (1024 * 1024 * 1024)} GB)",
        )

    ext = os.path.splitext(body.filename or "")[1].lower()
    if ext not in _ALLOWED_VIDEO_EXTS:
        ext = ".mp4"

    upload_id = str(uuid.uuid4())
    r2_key = f"upload_sources/{current_user['id']}/{upload_id}{ext}"

    try:
        from app.services.r2_client import create_multipart_upload
        mpu_upload_id = create_multipart_upload(r2_key, body.content_type)
    except Exception as e:
        print(f"[MpuInit] R2 create error: {e}")
        raise HTTPException(status_code=500, detail="Could not start multipart upload")

    try:
        get_client().table("video_uploads").insert({
            "id": upload_id,
            "user_id": current_user["id"],
            "r2_key": r2_key,
            "filename": body.filename,
            "content_type": body.content_type,
            "size_bytes": body.size_bytes,
            "mpu_upload_id": mpu_upload_id,
        }).execute()
    except Exception as e:
        # Best-effort: release the R2 multipart handle so storage doesn't leak.
        try:
            from app.services.r2_client import abort_multipart_upload
            abort_multipart_upload(r2_key, mpu_upload_id)
        except Exception:
            pass
        print(f"[MpuInit] DB insert error: {e}")
        raise HTTPException(status_code=500, detail="Could not register upload")

    print(f"[MpuInit] user={current_user['id']} id={upload_id} size={body.size_bytes}")
    return {
        "upload_id": upload_id,
        "r2_key": r2_key,
        "mpu_upload_id": mpu_upload_id,
        "min_part_size": _MPU_MIN_PART_SIZE,
        "max_parts": _MPU_MAX_PARTS,
    }


def _lookup_mpu_row(supabase, upload_id: str, user_id: str) -> dict:
    row = (
        supabase.table("video_uploads")
        .select("id,user_id,r2_key,mpu_upload_id,ready")
        .eq("id", upload_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="Upload not found")
    if not row.data.get("mpu_upload_id"):
        raise HTTPException(status_code=400, detail="This upload is not multipart")
    return row.data


@router.post("/mpu/sign-part")
@limiter.limit("1000/hour")
async def mpu_sign_part(
    request: Request,
    body: MpuSignPartBody,
    current_user: dict = Depends(get_current_user),
):
    """Return a short-lived presigned URL for a single part PUT."""
    if body.part_number < 1 or body.part_number > _MPU_MAX_PARTS:
        raise HTTPException(status_code=400, detail="part_number out of range")

    row = _lookup_mpu_row(get_client(), body.upload_id, current_user["id"])
    try:
        from app.services.r2_client import generate_presigned_upload_part
        url = generate_presigned_upload_part(
            row["r2_key"], row["mpu_upload_id"], body.part_number, expires_in=_MPU_PART_URL_TTL,
        )
    except Exception as e:
        print(f"[MpuSignPart] R2 sign error: {e}")
        raise HTTPException(status_code=500, detail="Could not sign part")
    return {"url": url, "part_number": body.part_number}


@router.post("/mpu/complete")
@limiter.limit("60/hour")
async def mpu_complete(
    request: Request,
    body: MpuCompleteBody,
    current_user: dict = Depends(get_current_user),
):
    """Finalize the multipart upload. Caller sends collected part ETags."""
    if not body.parts:
        raise HTTPException(status_code=400, detail="parts must not be empty")
    if len(body.parts) > _MPU_MAX_PARTS:
        raise HTTPException(status_code=400, detail="too many parts")

    row = _lookup_mpu_row(get_client(), body.upload_id, current_user["id"])

    # R2 requires ascending, contiguous part numbers starting at 1.
    ordered = sorted(body.parts, key=lambda p: p.part_number)
    for idx, p in enumerate(ordered, start=1):
        if p.part_number != idx:
            raise HTTPException(status_code=400, detail="parts must be contiguous starting at 1")
    s3_parts = [{"PartNumber": p.part_number, "ETag": p.etag} for p in ordered]

    try:
        from app.services.r2_client import complete_multipart_upload
        complete_multipart_upload(row["r2_key"], row["mpu_upload_id"], s3_parts)
    except Exception as e:
        print(f"[MpuComplete] R2 complete error: {e}")
        raise HTTPException(status_code=500, detail="Could not finalize upload")

    # Measure duration server-side (ffprobe over presigned GET), then mark ready.
    try:
        from app.services.r2_client import generate_presigned_get
        signed_get = generate_presigned_get(row["r2_key"], expires_in=600)
        duration = _probe_duration_from_url(signed_get)
    except Exception as e:
        print(f"[MpuComplete] ffprobe failed: {e}")
        duration = 0.0

    try:
        get_client().table("video_uploads").update({
            "duration_seconds": duration,
            "ready": True,
        }).eq("id", body.upload_id).eq("user_id", current_user["id"]).execute()
    except Exception as e:
        print(f"[MpuComplete] DB update error: {e}")

    print(f"[MpuComplete] id={body.upload_id} parts={len(ordered)} duration={duration:.1f}s")
    return {"ok": True, "upload_id": body.upload_id, "duration_seconds": duration}


@router.post("/mpu/abort")
@limiter.limit("60/hour")
async def mpu_abort(
    request: Request,
    body: MpuAbortBody,
    current_user: dict = Depends(get_current_user),
):
    """Abort a multipart upload. Frees storage for any parts already uploaded."""
    row = _lookup_mpu_row(get_client(), body.upload_id, current_user["id"])
    try:
        from app.services.r2_client import abort_multipart_upload
        abort_multipart_upload(row["r2_key"], row["mpu_upload_id"])
    except Exception as e:
        print(f"[MpuAbort] R2 abort error: {e}")
    try:
        get_client().table("video_uploads").delete().eq("id", body.upload_id).eq("user_id", current_user["id"]).execute()
    except Exception as e:
        print(f"[MpuAbort] DB delete error: {e}")
    return {"ok": True}


async def _fetch_upload_and_run_pipeline(
    job_id: str,
    upload_id: str,
    r2_key: str,
    ext: str,
    video_title: str,
    target_guest: Optional[str],
    metadata_subject_name: Optional[str],
    channel_id: str,
    user_id: str,
    clip_duration_min: Optional[int],
    clip_duration_max: Optional[int],
    trim_start_seconds: float = 0.0,
    trim_end_seconds: Optional[float] = None,
) -> None:
    """
    Background task for R2-uploaded videos. Downloads R2 object to local disk,
    applies optional trim, then runs the pipeline. This runs outside the HTTP
    request so multi-GB downloads can't hit Railway's ~10min HTTP timeout.
    """
    from app.pipeline.orchestrator import run_pipeline, update_job
    from app.services.r2_client import download_r2_to_local
    from app.services.supabase_client import get_client

    if ext not in _ALLOWED_VIDEO_EXTS:
        ext = ".mp4"
    from pathlib import Path
    upload_dir = Path(storage.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(upload_dir / f"{job_id}{ext}")
    trimmed_path: Optional[str] = None

    try:
        update_job(
            job_id,
            status=JobStatus.PROCESSING.value,
            current_step="fetching_upload",
            current_step_number=0,
            progress_pct=1,
        )
        print(f"[JobsRoute] Downloading upload {upload_id} from R2 → {video_path}")
        download_r2_to_local(r2_key, video_path)

        if trim_start_seconds > 0.0 or trim_end_seconds is not None:
            duration = get_video_duration(video_path)
            end = trim_end_seconds if trim_end_seconds is not None else duration
            if trim_start_seconds > 0.0 or end < duration:
                trimmed_path = video_path.replace(".", "_trimmed.", 1)
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(trim_start_seconds),
                    "-i", video_path,
                    "-t", str(end - trim_start_seconds),
                    "-c", "copy",
                    trimmed_path,
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if result.returncode == 0 and os.path.exists(trimmed_path):
                    try:
                        os.remove(video_path)
                    except Exception:
                        pass
                    video_path = trimmed_path
                    trimmed_path = None
                else:
                    print(f"[JobsRoute] Trim failed, using full video: {result.stderr}")

        get_client().table("jobs").update({"video_path": video_path}).eq("id", job_id).execute()

        # --- CLIENT CREDIT RESERVATION (after trim, before pipeline) ---
        from app.middleware.roles import is_client_user
        from app.services.credits import calculate_credits_needed, reserve_credits
        if is_client_user(user_id):
            final_duration = get_video_duration(video_path)
            if final_duration < 60.0:
                update_job(job_id, status=JobStatus.FAILED.value, error_message="Video must be at least 60 seconds after trimming.")
                return
            credits_needed = calculate_credits_needed(final_duration)
            reserved = reserve_credits(user_id, job_id, credits_needed)
            if not reserved:
                update_job(job_id, status=JobStatus.FAILED.value, error_message="Insufficient credits to process this video.")
                return
            get_client().table("jobs").update({"credit_reserved": credits_needed}).eq("id", job_id).execute()

        # Run sync pipeline in a worker thread so the event loop stays free.
        # Without this, Modal's sync calls block the loop, print buffers stall,
        # and Modal itself warns about blocking interfaces inside async context.
        import asyncio
        await asyncio.to_thread(
            run_pipeline, job_id, video_path, video_title, target_guest,
            channel_id, user_id, clip_duration_min, clip_duration_max,
            metadata_subject_name,
        )
    except Exception as e:
        print(f"[JobsRoute] R2 fetch/pipeline failed for job {job_id}: {e}")
        update_job(job_id, status=JobStatus.FAILED.value, error_message=f"Upload fetch failed: {e}")
        # Let user retry — release the claim
        try:
            get_client().table("video_uploads").update({"consumed": False}).eq("id", upload_id).execute()
        except Exception:
            pass
        for path in [video_path, trimmed_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
    finally:
        # Delete upload_sources R2 object — pipeline has it locally now, no longer needed
        try:
            from app.services.r2_client import get_r2_client
            from app.config import settings as _s
            get_r2_client().delete_object(Bucket=_s.R2_BUCKET_NAME, Key=r2_key)
            print(f"[JobsRoute] Deleted upload_sources R2 object: {r2_key}")
        except Exception as _e:
            print(f"[JobsRoute] upload_sources R2 delete error (non-critical): {_e}")


async def _download_and_run_pipeline(
    job_id: str,
    youtube_url: str,
    video_title: str,
    target_guest: Optional[str],
    metadata_subject_name: Optional[str],
    channel_id: str,
    user_id: str,
    clip_duration_min: Optional[int],
    clip_duration_max: Optional[int],
    trim_start_seconds: float = 0.0,
    trim_end_seconds: Optional[float] = None,
) -> None:
    """Background task: downloads YouTube video, applies trim if needed, then runs pipeline."""
    from app.services.video_downloader import VideoDownloader
    from app.pipeline.orchestrator import run_pipeline, update_job
    from app.models.enums import JobStatus
    from app.services.supabase_client import get_client

    downloader = VideoDownloader()
    video_path = None
    trimmed_path = None
    try:
        update_job(
            job_id,
            status=JobStatus.PROCESSING.value,
            current_step="downloading_video",
            current_step_number=0,
            progress_pct=2,
        )
        print(f"[JobsRoute] Downloading YouTube video for job {job_id}: {youtube_url}")
        video_path = await downloader.download(youtube_url, max_quality="1080")
        print(f"[JobsRoute] Download complete: {video_path}")

        # Apply trim if requested
        if trim_start_seconds > 0.0 or trim_end_seconds is not None:
            duration = get_video_duration(video_path)
            end = trim_end_seconds if trim_end_seconds is not None else duration
            if trim_start_seconds > 0.0 or end < duration:
                trimmed_path = video_path.replace(".", "_trimmed.", 1)
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(trim_start_seconds),
                    "-i", video_path,
                    "-t", str(end - trim_start_seconds),
                    "-c", "copy",
                    trimmed_path,
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if result.returncode == 0 and os.path.exists(trimmed_path):
                    os.remove(video_path)
                    video_path = trimmed_path
                    trimmed_path = None
                else:
                    print(f"[JobsRoute] Trim failed, using full video: {result.stderr}")

        get_client().table("jobs").update({"video_path": video_path}).eq("id", job_id).execute()

        # --- CLIENT CREDIT RESERVATION (after trim, before pipeline) ---
        from app.middleware.roles import is_client_user
        from app.services.credits import calculate_credits_needed, reserve_credits
        if is_client_user(user_id):
            final_duration = get_video_duration(video_path)
            if final_duration < 60.0:
                update_job(job_id, status=JobStatus.FAILED.value, error_message="Video must be at least 60 seconds after trimming.")
                return
            credits_needed = calculate_credits_needed(final_duration)
            reserved = reserve_credits(user_id, job_id, credits_needed)
            if not reserved:
                update_job(job_id, status=JobStatus.FAILED.value, error_message="Insufficient credits to process this video.")
                return
            get_client().table("jobs").update({"credit_reserved": credits_needed}).eq("id", job_id).execute()

        # Run sync pipeline in a worker thread so the event loop stays free.
        import asyncio
        await asyncio.to_thread(
            run_pipeline, job_id, video_path, video_title, target_guest,
            channel_id, user_id, clip_duration_min, clip_duration_max,
            metadata_subject_name,
        )
    except Exception as e:
        print(f"[JobsRoute] YouTube download failed for job {job_id}: {e}")
        update_job(job_id, status=JobStatus.FAILED.value, error_message=f"YouTube download failed: {e}")
        for path in [video_path, trimmed_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


@router.get("/youtube-info")
async def get_youtube_info(url: str, current_user: dict = Depends(get_current_user)):
    """Fetch YouTube video metadata (title, duration) without downloading."""
    from app.services.video_downloader import VideoDownloader
    if not any(h in url for h in ("youtube.com/watch", "youtu.be/", "youtube.com/shorts/")):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    try:
        downloader = VideoDownloader()
        info = await downloader.get_info(url)
        return {
            "title": info.get("title", ""),
            "duration_seconds": info.get("duration", 0),
            "thumbnail": info.get("thumbnail", ""),
            "channel": info.get("uploader", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not fetch video info: {e}")


@router.post("")
@limiter.limit("20/hour")
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    upload_id: str = Form(None),
    video: UploadFile = File(None),
    youtube_url: Optional[str] = Form(None),
    title: str = Form(...),
    target_guest: Optional[str] = Form(None),
    metadata_subject_name: Optional[str] = Form(None),
    channel_id: str = Form(...),
    trim_start_seconds: float = Form(0.0),
    trim_end_seconds: float = Form(None),
    clip_duration_min: Optional[int] = Form(None),
    clip_duration_max: Optional[int] = Form(None),
    aspect_ratio: Optional[str] = Form(None),
    genre: Optional[str] = Form(None),
    auto_hook: Optional[str] = Form(None),
    reframe_content_type: Optional[str] = Form(None),
    caption_template: Optional[str] = Form(None),
    s05_model: Optional[str] = Form(None),
    s06_model: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    channel_id = channel_id.replace("-", "_")
    try:
        job_id = str(uuid.uuid4())
        r2_upload_row: Optional[dict] = None
        r2_upload_ext: Optional[str] = None
        metadata_subject_name = metadata_subject_name.strip() if metadata_subject_name and metadata_subject_name.strip() else None

        if youtube_url:
            # Validate it's a real YouTube URL
            if not any(host in youtube_url for host in ("youtube.com/watch", "youtu.be/", "youtube.com/shorts/")):
                raise HTTPException(status_code=400, detail="Invalid YouTube URL. Supported: youtube.com/watch, youtu.be, youtube.com/shorts")
            video_path = ""  # Will be set by background downloader

        elif upload_id:
            # 1. Legacy path: local temp_uploads/ (old upload-preview flow)
            upload_dir = storage.UPLOAD_DIR
            video_path = None
            try:
                for f in os.listdir(upload_dir):
                    if f.startswith(upload_id):
                        video_path = os.path.join(upload_dir, f)
                        break
            except FileNotFoundError:
                video_path = None

            # 2. New path: presigned direct upload. Validate the row, claim it, and
            # DEFER the actual R2 download to a background task — multi-GB downloads
            # would otherwise exceed Railway's HTTP timeout and cause 500/404 retries.
            if not video_path:
                sb = get_client()
                vu = (
                    sb.table("video_uploads")
                    .select("*")
                    .eq("id", upload_id)
                    .eq("user_id", current_user["id"])
                    .eq("ready", True)
                    .eq("consumed", False)
                    .limit(1)
                    .execute()
                )
                if not vu.data:
                    raise HTTPException(status_code=404, detail="Uploaded file not found.")
                r2_upload_row = vu.data[0]

                # Atomic claim — flip consumed=true; if another request won, bail
                claim = (
                    sb.table("video_uploads")
                    .update({"consumed": True})
                    .eq("id", upload_id)
                    .eq("consumed", False)
                    .execute()
                )
                if not claim.data:
                    raise HTTPException(status_code=409, detail="Upload already consumed.")

                r2_upload_ext = os.path.splitext(r2_upload_row.get("filename") or "")[1].lower()
                if r2_upload_ext not in _ALLOWED_VIDEO_EXTS:
                    r2_upload_ext = ".mp4"
                # Placeholder path — real path is written by background task once R2
                # download finishes. Pipeline never sees this placeholder.
                video_path = f"pending_r2:{upload_id}"

        elif video:
            # YÜKS-3: Validate MIME type
            if video.content_type not in _ALLOWED_VIDEO_TYPES:
                raise HTTPException(status_code=400, detail="Uploaded file is not a supported video format.")

            # YÜKS-3: Sanitize filename
            original_ext = os.path.splitext(video.filename or "")[1].lower()
            if original_ext not in _ALLOWED_VIDEO_EXTS:
                original_ext = ".mp4"
            safe_name = f"{job_id}{original_ext}"

            file_bytes = await video.read()
            video_path = storage.save_upload(file_bytes, safe_name, job_id)
            if not video_path:
                raise HTTPException(status_code=500, detail="Failed to save video file.")
        else:
            raise HTTPException(status_code=400, detail="Must provide youtube_url, upload_id, or video file.")
            
        # Trimming logic (skip for YouTube + R2-pending uploads — those trim in the background task)
        _defer_to_background = youtube_url or (upload_id and r2_upload_row is not None)
        if not _defer_to_background and (trim_start_seconds > 0.0 or (trim_end_seconds is not None)):
            duration = get_video_duration(video_path)
            if trim_end_seconds is None:
                trim_end_seconds = duration
            
            if trim_start_seconds > 0.0 or trim_end_seconds < duration:
                # Need to trim
                trimmed_filename = f"trimmed_{os.path.basename(video_path)}"
                trimmed_path = os.path.join(os.path.dirname(video_path), trimmed_filename)
                
                trim_duration = trim_end_seconds - trim_start_seconds
                
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(trim_start_seconds),
                    "-i", video_path,
                    "-t", str(trim_duration),
                    "-c", "copy",
                    trimmed_path
                ]
                
                print(f"[JobsRoute] Trimming video")
                try:
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
                    video_path = trimmed_path
                except Exception as e:
                    print(f"[JobsRoute] Error trimming video: {e}")
                    # Clean up temp file on trim failure
                    if os.path.exists(trimmed_path):
                        os.remove(trimmed_path)
                    raise HTTPException(status_code=500, detail="Failed to trim video.")
            
        supabase = get_client()

        # Verify channel belongs to current user
        channel_check = supabase.table("channels").select("id").eq("id", channel_id).eq("user_id", current_user["id"]).execute()
        if not channel_check.data:
            raise HTTPException(status_code=404, detail="Channel not found")

        # --- CLIENT CREDIT PRE-CHECK ---
        from app.middleware.roles import is_client_user
        from app.services.credits import get_balance, check_concurrent_jobs
        _is_client = is_client_user(current_user["id"])
        if _is_client:
            credit_info = get_balance(current_user["id"])
            if not credit_info:
                raise HTTPException(status_code=403, detail="Client account not configured. Contact administrator.")
            if credit_info.get("is_locked"):
                raise HTTPException(status_code=403, detail="Account locked due to repeated failures. Contact administrator.")
            if credit_info.get("balance", 0) <= 0:
                raise HTTPException(status_code=402, detail="Insufficient credits. Request more credits to continue.")
            active_jobs = check_concurrent_jobs(current_user["id"])
            max_jobs = credit_info.get("max_concurrent_jobs", 2)
            if active_jobs >= max_jobs:
                raise HTTPException(status_code=429, detail=f"Maximum {max_jobs} concurrent jobs allowed. Wait for current jobs to complete.")

        # Insert job into Supabase
        # Log new clip settings for future pipeline use
        if clip_duration_min is not None or clip_duration_max is not None:
            print(f"[JobsRoute] Clip duration: {clip_duration_min}–{clip_duration_max}s, aspect: {aspect_ratio}, genre: {genre}, auto_hook: {auto_hook}")

        # Per-step Claude model is an admin measurement tool. The selector is
        # hidden for clients, but the UI is not the gate — a hand-rolled POST
        # would otherwise let a client account bill the platform's Anthropic
        # key. Unknown values are dropped rather than rejected so an outdated
        # client just gets the default behaviour.
        from app.middleware.roles import is_admin_user
        _ALLOWED_MODELS = ("opus-5", "opus-4-6")
        if not is_admin_user(current_user["id"]):
            s05_model = s06_model = None
        s05_model = s05_model if s05_model in _ALLOWED_MODELS else None
        s06_model = s06_model if s06_model in _ALLOWED_MODELS else None

        job_data = {
            "id": job_id,
            "channel_id": channel_id,
            "user_id": current_user["id"],
            "video_title": title,
            "target_guest": target_guest,
            "status": JobStatus.QUEUED.value,
            "current_step": "queued",
            "progress_pct": 0,
            "video_path": video_path,
            "trim_start_seconds": trim_start_seconds,
            "trim_end_seconds": trim_end_seconds,
        }
        if clip_duration_min is not None:
            job_data["clip_duration_min"] = clip_duration_min
        if clip_duration_max is not None:
            job_data["clip_duration_max"] = clip_duration_max
        if reframe_content_type in ("podcast", "gaming"):
            job_data["reframe_content_type"] = reframe_content_type
        if caption_template:
            job_data["caption_template"] = caption_template
        if s05_model:
            job_data["s05_model"] = s05_model
        if s06_model:
            job_data["s06_model"] = s06_model

        response = supabase.table("jobs").insert(job_data).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create job in database.")
            
        # Add pipeline task to background
        if youtube_url:
            background_tasks.add_task(
                _download_and_run_pipeline,
                job_id,
                youtube_url,
                title,
                target_guest,
                metadata_subject_name,
                channel_id,
                current_user["id"],
                clip_duration_min,
                clip_duration_max,
                trim_start_seconds,
                trim_end_seconds,
            )
        elif upload_id and r2_upload_row is not None:
            background_tasks.add_task(
                _fetch_upload_and_run_pipeline,
                job_id,
                upload_id,
                r2_upload_row["r2_key"],
                r2_upload_ext or ".mp4",
                title,
                target_guest,
                metadata_subject_name,
                channel_id,
                current_user["id"],
                clip_duration_min,
                clip_duration_max,
                trim_start_seconds,
                trim_end_seconds,
            )
        else:
            # For local uploads, video is already trimmed — reserve credits now
            if _is_client:
                from app.services.credits import calculate_credits_needed, reserve_credits
                final_duration = get_video_duration(video_path)
                if final_duration < 60.0:
                    raise HTTPException(status_code=400, detail="Video must be at least 60 seconds after trimming.")
                credits_needed = calculate_credits_needed(final_duration)
                reserved = reserve_credits(current_user["id"], job_id, credits_needed)
                if not reserved:
                    raise HTTPException(status_code=402, detail="Insufficient credits to process this video.")
                supabase.table("jobs").update({"credit_reserved": credits_needed}).eq("id", job_id).execute()

            background_tasks.add_task(
                run_pipeline,
                job_id,
                video_path,
                title,
                target_guest,
                channel_id,
                current_user["id"],
                clip_duration_min,
                clip_duration_max,
                metadata_subject_name,
            )

        print(f"[JobsRoute] Started job {job_id} for video '{title}'" + (" (YouTube)" if youtube_url else ""))
        return {"job_id": job_id, "status": "queued", "message": "Processing started"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[JobsRoute] Error in POST /jobs: {e}")
        raise HTTPException(status_code=500, detail="Job creation failed")


@router.post("/youtube-preview")
@limiter.limit("5/minute")
async def youtube_preview(
    request: Request,
    url: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Downloads a YouTube video (up to 1080p) to temp storage for preview.
    Returns upload_id and duration so the frontend can show a real <video> element
    and re-use the pre-downloaded file when starting the pipeline.
    """
    from app.services.video_downloader import VideoDownloader

    if not any(h in url for h in ("youtube.com/watch", "youtu.be/", "youtube.com/shorts/")):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    try:
        downloader = VideoDownloader()
        video_path = await downloader.download(url, max_quality="1080")
        upload_id = os.path.splitext(os.path.basename(video_path))[0]
        duration = get_video_duration(video_path)
        print(f"[YoutubePreview] Downloaded {upload_id}, duration: {duration:.1f}s")
        return {"upload_id": upload_id, "duration_seconds": duration}
    except Exception as e:
        print(f"[YoutubePreview] Error: {e}")
        raise HTTPException(status_code=422, detail=f"Could not download video: {e}")


@router.get("/video-stream/{upload_id}")
async def video_stream(upload_id: str, current_user: dict = Depends(get_current_user)):
    """Stream a pre-downloaded temp video file for browser preview."""
    import re
    from fastapi.responses import FileResponse

    if not re.match(r"^[a-f0-9\-]{36}$", upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload ID")

    upload_dir = settings.UPLOAD_DIR
    for fname in os.listdir(upload_dir):
        if os.path.splitext(fname)[0] == upload_id:
            file_path = os.path.join(upload_dir, fname)
            return FileResponse(file_path, media_type="video/mp4")

    raise HTTPException(status_code=404, detail="File not found")


@router.get("/{job_id}")
async def get_job(job_id: str, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        
        # Query job (ownership check via user_id)
        job_response = supabase.table("jobs").select("*").eq("id", job_id).eq("user_id", current_user["id"]).execute()
        if not job_response.data:
            raise HTTPException(status_code=404, detail="Job not found")
            
        job = job_response.data[0]
        
        # Query clips
        clips_response = supabase.table("clips").select("*").eq("job_id", job_id).order("posting_order").execute()
        
        # Also fetch transcript speaker_map
        transcript_res = supabase.table("transcripts").select("speaker_map").eq("job_id", job_id).execute()
        speaker_map = {}
        if transcript_res.data:
            speaker_map = transcript_res.data[0].get("speaker_map", {})
        
        print(f"[JobsRoute] Fetched job {job_id}")
        return {
            "job": job,
            "clips": clips_response.data if clips_response.data else [],
            "speaker_map": speaker_map
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[JobsRoute] Error in GET /jobs/{job_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{job_id}/reviewed")
async def set_job_reviewed(
    job_id: str,
    reviewed: bool = Body(default=True, embed=True),
    current_user: dict = Depends(get_current_user),
):
    """
    Marks a job as gone through — its clips have been looked at and the good
    ones picked, so it needs no second pass. A single boolean rather than the
    tri-state the clips routes use: a project is either reviewed or it is not.
    """
    try:
        supabase = get_client()

        check = supabase.table("jobs").select("id").eq("id", job_id).eq("user_id", current_user["id"]).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Job not found")

        reviewed_at = datetime.now(timezone.utc).isoformat() if reviewed else None
        supabase.table("jobs").update({"reviewed_at": reviewed_at}).eq("id", job_id).execute()

        return {"job_id": job_id, "reviewed_at": reviewed_at}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[JobsRoute] Error setting reviewed on {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("")
async def list_jobs(channel_id: str, limit: int = 20, current_user: dict = Depends(get_current_user)):
    channel_id = channel_id.replace("-", "_")
    try:
        supabase = get_client()
        
        jobs_response = supabase.table("jobs").select("*").eq("channel_id", channel_id).eq("user_id", current_user["id"]).order("created_at", desc=True).limit(limit).execute()
        
        return jobs_response.data if jobs_response.data else []
        
    except Exception as e:
        print(f"[JobsRoute] Error in GET /jobs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{job_id}")
async def delete_job(job_id: str, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()

        # Verify ownership before deleting
        check = supabase.table("jobs").select("id").eq("id", job_id).eq("user_id", current_user["id"]).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Cascade R2 cleanup — remove every clip's remote asset for this job.
        try:
            from app.services.r2_client import delete_prefix, delete_url
            clips_res = (
                supabase.table("clips")
                .select("video_captioned_path,video_reframed_path,file_url")
                .eq("job_id", job_id)
                .execute()
            )
            for c in clips_res.data or []:
                for url in [
                    c.get("video_captioned_path"),
                    c.get("video_reframed_path"),
                    c.get("file_url"),
                ]:
                    if url:
                        delete_url(url)
            # Also remove any leftover prefixes for this job.
            delete_prefix(f"{job_id}/")
            delete_prefix(f"source_videos/{job_id}/")
            delete_prefix(f"gaming-reframe/{job_id}/")
        except Exception as _e:
            print(f"[JobsRoute] R2 cascade warning: {_e}")

        # Delete clips
        supabase.table("clips").delete().eq("job_id", job_id).execute()

        # Delete job
        job_response = supabase.table("jobs").delete().eq("id", job_id).execute()
        if not job_response.data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Delete output directory for job using storage
        job_dir = os.path.join(storage.OUTPUT_DIR, job_id)
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
            print(f"[JobsRoute] Deleted output directory: {job_dir}")

        print(f"[JobsRoute] Deleted job {job_id}")
        return {"deleted": True, "job_id": job_id}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[JobsRoute] Error in DELETE /jobs/{job_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
