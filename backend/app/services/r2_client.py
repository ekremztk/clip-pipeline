import os
import re
import unicodedata
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError
from app.config import settings


def generate_presigned_put(key: str, content_type: str, expires_in: int = 3600) -> str:
    """Generate a presigned PUT URL so the browser can upload directly to R2."""
    s3 = get_r2_client()
    return s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.R2_BUCKET_NAME,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in,
    )


def create_multipart_upload(key: str, content_type: str) -> str:
    """Start an S3 multipart upload on R2. Returns the UploadId."""
    s3 = get_r2_client()
    resp = s3.create_multipart_upload(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        ContentType=content_type,
    )
    return resp["UploadId"]


def generate_presigned_upload_part(
    key: str, upload_id: str, part_number: int, expires_in: int = 3600
) -> str:
    """Presigned PUT URL for a single part of a multipart upload."""
    s3 = get_r2_client()
    return s3.generate_presigned_url(
        "upload_part",
        Params={
            "Bucket": settings.R2_BUCKET_NAME,
            "Key": key,
            "UploadId": upload_id,
            "PartNumber": part_number,
        },
        ExpiresIn=expires_in,
    )


def complete_multipart_upload(key: str, upload_id: str, parts: list[dict]) -> dict:
    """
    Complete a multipart upload. `parts` must be a list of
    {"PartNumber": int, "ETag": str} sorted by PartNumber ascending.
    """
    s3 = get_r2_client()
    return s3.complete_multipart_upload(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={"Parts": parts},
    )


def abort_multipart_upload(key: str, upload_id: str) -> None:
    """Abort a multipart upload to free storage of any uploaded parts."""
    s3 = get_r2_client()
    s3.abort_multipart_upload(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        UploadId=upload_id,
    )


def download_r2_to_local(r2_key: str, local_path: str) -> None:
    """Stream-download an R2 object to disk without buffering in memory."""
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    s3 = get_r2_client()
    s3.download_file(settings.R2_BUCKET_NAME, r2_key, local_path)


def generate_presigned_get(key: str, expires_in: int = 3600) -> str:
    """Presigned GET URL so remote tools (ffprobe/ffmpeg) can read without credentials."""
    s3 = get_r2_client()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )


def generate_presigned_download(key: str, filename: str, expires_in: int = 3600) -> str:
    """Presigned GET URL with a browser download filename."""
    s3 = get_r2_client()
    safe_filename = _safe_download_filename(filename)
    ascii_fallback = _ascii_download_filename(safe_filename)
    disposition = (
        f"attachment; filename=\"{ascii_fallback}\"; "
        f"filename*=UTF-8''{quote(safe_filename, safe='')}"
    )
    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.R2_BUCKET_NAME,
            "Key": key,
            "ResponseContentDisposition": disposition,
        },
        ExpiresIn=expires_in,
    )


def _safe_download_filename(filename: str) -> str:
    value = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "", filename or "").strip(" .")
    value = re.sub(r"\s+", " ", value)
    if not value:
        value = "download.mp4"
    if not value.lower().endswith(".mp4"):
        value = f"{value}.mp4"
    stem, ext = os.path.splitext(value)
    if len(stem) > 140:
        stem = stem[:140].rstrip(" .")
    return f"{stem}{ext}"


def _ascii_download_filename(filename: str) -> str:
    stem, ext = os.path.splitext(filename)
    ascii_stem = (
        unicodedata.normalize("NFKD", stem)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    ascii_stem = re.sub(r"[^A-Za-z0-9._ -]+", "", ascii_stem).strip(" .")
    if not ascii_stem:
        ascii_stem = "download"
    return f"{ascii_stem}{ext or '.mp4'}"


def object_exists(key: str) -> bool:
    """HEAD an R2 object; True if found, False if 404."""
    s3 = get_r2_client()
    try:
        s3.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        return True
    except ClientError:
        return False


def delete_prefix(prefix: str) -> int:
    """
    Delete ALL objects under a given R2 prefix. Returns count deleted.
    Safe to call with empty prefix check (refuses "" and "/").
    """
    if not prefix or prefix.strip("/") == "":
        raise ValueError("delete_prefix: empty prefix refused for safety")
    bucket = settings.R2_BUCKET_NAME
    if not bucket:
        raise ValueError("R2_BUCKET_NAME not set")

    s3 = get_r2_client()
    paginator = s3.get_paginator("list_objects_v2")
    total_deleted = 0
    batch: list[dict] = []

    def _flush(keys: list[dict]) -> int:
        if not keys:
            return 0
        s3.delete_objects(
            Bucket=bucket,
            Delete={"Objects": keys, "Quiet": True},
        )
        return len(keys)

    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                batch.append({"Key": obj["Key"]})
                if len(batch) >= 1000:
                    total_deleted += _flush(batch)
                    batch = []
        total_deleted += _flush(batch)
        return total_deleted
    except ClientError as e:
        print(f"[R2Client] delete_prefix({prefix}) error: {e}")
        return total_deleted


def delete_url(url: str) -> bool:
    """Delete a single R2 object given its public URL. Returns True on success."""
    public_base = (settings.R2_PUBLIC_URL or "").rstrip("/")
    if not public_base or not url or not url.startswith(public_base):
        return False
    key = url[len(public_base) + 1:]
    if not key:
        return False
    try:
        s3 = get_r2_client()
        s3.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        return True
    except ClientError as e:
        print(f"[R2Client] delete_url({url}) error: {e}")
        return False


def get_r2_client():
    if not settings.R2_ACCOUNT_ID:
        raise ValueError("R2_ACCOUNT_ID is not set in environment variables.")
        
    endpoint_url = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    
    return boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto" # R2 requires region to be 'auto' or omited, boto3 needs it
    )


def upload_clip(job_id: str, filename: str, file_path: str) -> str:
    """
    Uploads a clip to Cloudflare R2 and returns the public URL.
    """
    try:
        s3 = get_r2_client()
        bucket_name = settings.R2_BUCKET_NAME
        
        if not bucket_name:
            raise ValueError("R2_BUCKET_NAME is not set.")
            
        object_name = f"{job_id}/{filename}"
        
        # Read file as bytes and upload
        with open(file_path, "rb") as f:
            file_data = f.read()
            
        s3.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=file_data,
            ContentType="video/mp4" # Assuming mp4 clips
        )
        
        public_url = settings.R2_PUBLIC_URL
        if not public_url:
            raise ValueError("R2_PUBLIC_URL is not set.")
            
        # Ensure public URL doesn't have trailing slash for clean concatenation
        public_url = public_url.rstrip('/')
        return f"{public_url}/{object_name}"
        
    except Exception as e:
        print(f"[R2Client] Error uploading {filename} to R2: {e}")
        raise
