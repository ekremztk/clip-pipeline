import os
import boto3
from botocore.exceptions import ClientError
from app.config import settings

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

def upload_srt(job_id: str, filename: str, content: str) -> str:
    """
    Uploads an SRT subtitle file (string) to Cloudflare R2 and returns the public URL.
    """
    try:
        s3 = get_r2_client()
        bucket_name = settings.R2_BUCKET_NAME

        if not bucket_name:
            raise ValueError("R2_BUCKET_NAME is not set.")

        object_name = f"{job_id}/{filename}"

        s3.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=content.encode("utf-8"),
            ContentType="text/plain; charset=utf-8"
        )

        public_url = settings.R2_PUBLIC_URL.rstrip("/")
        return f"{public_url}/{object_name}"

    except Exception as e:
        print(f"[R2Client] Error uploading SRT {filename} to R2: {e}")
        raise


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
