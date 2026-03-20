# EDITOR MODULE — Isolated module, no dependencies on other project files

import os
import uuid
import boto3
import logging
import asyncio
from typing import Dict, Optional
from google.cloud import storage as gcs
from botocore.exceptions import ClientError
from google.api_core.exceptions import GoogleAPIError

from editor_config import (
    R2_ENDPOINT_URL,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_EDITOR_BUCKET_NAME,
    GCS_EDITOR_BUCKET_NAME
)

logger = logging.getLogger("editor.storage")

def get_r2_client():
    if not all([R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
        raise ValueError("Missing R2 credentials")
    
    return boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY
    )

def get_gcs_client() -> gcs.Client:
    return gcs.Client()

async def generate_upload_presigned_url(filename: str, content_type: str) -> Dict[str, str]:
    """
    Generates a presigned URL for uploading a file to R2.
    """
    try:
        s3_client = get_r2_client()
        key = f"uploads/{uuid.uuid4()}/{filename}"
        
        def _generate():
            return s3_client.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': R2_EDITOR_BUCKET_NAME,
                    'Key': key,
                    'ContentType': content_type
                },
                ExpiresIn=3600
            )
            
        url = await asyncio.to_thread(_generate)
        return {"url": url, "key": key}
    except ClientError as e:
        logger.error(f"R2 ClientError generating upload url for {filename}: {e}")
        raise RuntimeError(f"Storage error: {e}") from e
    except Exception as e:
        logger.error(f"Error generating upload url for {filename}: {e}")
        raise RuntimeError(f"Storage error: {e}") from e

async def generate_download_presigned_url(key: str, expires_in: int = 3600) -> str:
    """
    Generates a presigned URL for downloading a file from R2.
    """
    try:
        s3_client = get_r2_client()
        
        def _generate():
            return s3_client.generate_presigned_url(
                ClientMethod='get_object',
                Params={
                    'Bucket': R2_EDITOR_BUCKET_NAME,
                    'Key': key
                },
                ExpiresIn=expires_in
            )
            
        url = await asyncio.to_thread(_generate)
        return url
    except ClientError as e:
        logger.error(f"R2 ClientError generating download url for {key}: {e}")
        raise RuntimeError(f"Storage error: {e}") from e
    except Exception as e:
        logger.error(f"Error generating download url for {key}: {e}")
        raise RuntimeError(f"Storage error: {e}") from e

async def delete_r2_object(key: str) -> None:
    """
    Deletes an object from R2.
    """
    try:
        s3_client = get_r2_client()
        
        def _delete():
            s3_client.delete_object(
                Bucket=R2_EDITOR_BUCKET_NAME,
                Key=key
            )
            
        await asyncio.to_thread(_delete)
    except ClientError as e:
        logger.error(f"R2 ClientError deleting object {key}: {e}")
        raise RuntimeError(f"Storage error: {e}") from e
    except Exception as e:
        logger.error(f"Error deleting object {key} from R2: {e}")
        raise RuntimeError(f"Storage error: {e}") from e

async def copy_r2_to_gcs(r2_key: str, gcs_key: str) -> str:
    """
    Copies a file from R2 to GCS by writing to a temporary file on disk first,
    to avoid loading the entire file into memory (preventing OOM on 8GB RAM Railway).
    Returns the gs:// URI.
    """
    temp_file_path = f"/tmp/{uuid.uuid4()}_temp_download"
    try:
        s3_client = get_r2_client()
        gcs_client = get_gcs_client()
        
        def _download():
            s3_client.download_file(
                Bucket=R2_EDITOR_BUCKET_NAME,
                Key=r2_key,
                Filename=temp_file_path
            )
            
        # Download from R2 to disk
        await asyncio.to_thread(_download)
        
        # Upload from disk to GCS
        bucket = gcs_client.bucket(GCS_EDITOR_BUCKET_NAME)
        blob = bucket.blob(gcs_key)
        
        def _upload():
            blob.upload_from_filename(temp_file_path)
            
        await asyncio.to_thread(_upload)
        
        return f"gs://{GCS_EDITOR_BUCKET_NAME}/{gcs_key}"
        
    except ClientError as e:
        logger.error(f"R2 ClientError during copy for {r2_key}: {e}")
        raise RuntimeError(f"Storage error: {e}") from e
    except GoogleAPIError as e:
        logger.error(f"GCS error during copy for {gcs_key}: {e}")
        raise RuntimeError(f"Storage error: {e}") from e
    except Exception as e:
        logger.error(f"Error copying from R2 ({r2_key}) to GCS ({gcs_key}): {e}")
        raise RuntimeError(f"Storage error: {e}") from e
    finally:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_file_path}: {e}")

async def delete_gcs_object(gcs_key: str) -> None:
    """
    Deletes an object from GCS.
    """
    try:
        gcs_client = get_gcs_client()
        bucket = gcs_client.bucket(GCS_EDITOR_BUCKET_NAME)
        blob = bucket.blob(gcs_key)
        
        def _check_and_delete():
            if blob.exists():
                blob.delete()
                
        await asyncio.to_thread(_check_and_delete)
            
    except GoogleAPIError as e:
        logger.error(f"GCS error deleting object {gcs_key}: {e}")
        raise RuntimeError(f"Storage error: {e}") from e
    except Exception as e:
        logger.error(f"Error deleting object {gcs_key} from GCS: {e}")
        raise RuntimeError(f"Storage error: {e}") from e

def upload_local_to_gcs(local_path: str, gcs_key: str) -> str:
    """
    Upload an already-downloaded local file directly to GCS.
    Used instead of copy_r2_to_gcs to avoid re-downloading from R2.
    Returns the gs:// URI.
    Use streaming upload to avoid loading the full file into memory.
    """
    try:
        gcs_client = get_gcs_client()
        bucket = gcs_client.bucket(GCS_EDITOR_BUCKET_NAME)
        blob = bucket.blob(gcs_key)
        
        # Setting chunk_size enables streaming uploads, preventing OOM issues
        # 5MB chunk size is a reasonable default
        blob.chunk_size = 5 * 1024 * 1024
        
        blob.upload_from_filename(local_path)
        
        return f"gs://{GCS_EDITOR_BUCKET_NAME}/{gcs_key}"
        
    except GoogleAPIError as e:
        logger.error(f"GCS error uploading {local_path} to {gcs_key}: {e}")
        raise RuntimeError(f"Storage error: {e}") from e
    except Exception as e:
        logger.error(f"Error uploading {local_path} to GCS ({gcs_key}): {e}")
        raise RuntimeError(f"Storage error: {e}") from e
