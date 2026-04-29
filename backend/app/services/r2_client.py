import os
import boto3
from botocore.exceptions import ClientError
from app.config import settings


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
