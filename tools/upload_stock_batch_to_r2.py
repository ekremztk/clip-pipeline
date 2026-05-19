"""Upload a dated stock source batch folder to Cloudflare R2.

Expected local layout:
  ~/Source Videos/{Channel Name}/{Batch Name}/
    Source/
    Clipped/
    manifest.json

R2 key layout:
  stock_sources/{channel_id}/{batch_id}/{group}/{filename}.mp4
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


DEFAULT_ENV_FILE = Path("backend/.env")
DEFAULT_GROUP = "source"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def r2_client():
    account_id = require_env("R2_ACCOUNT_ID")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=require_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=require_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def safe_key_name(filename: str) -> str:
    value = filename.replace("\\", " ").replace("/", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def public_url(key: str) -> str:
    base = require_env("R2_PUBLIC_URL").rstrip("/")
    return f"{base}/{quote(key, safe='/')}"


def object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def load_local_manifest(batch_dir: Path) -> dict:
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.exists():
        return {"items": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def manifest_items_by_video_id(manifest: dict) -> dict[str, dict]:
    items = {}
    for item in manifest.get("items", []):
        video_id = item.get("video_id")
        if video_id:
            items[video_id] = item
    return items


def video_id_from_filename(path: Path) -> str | None:
    match = re.search(r"\[([A-Za-z0-9_-]{11})\]\.mp4$", path.name)
    return match.group(1) if match else None


def iter_video_files(batch_dir: Path) -> list[Path]:
    source_dir = batch_dir / "Source"
    if not source_dir.exists():
        raise RuntimeError(f"Source folder does not exist: {source_dir}")
    return sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".mp4"
    )


def build_key(channel_id: str, batch_id: str, group: str, path: Path) -> str:
    return f"stock_sources/{channel_id}/{batch_id}/{group}/{safe_key_name(path.name)}"


def upload_file(client, bucket: str, path: Path, key: str, force: bool) -> dict:
    size_bytes = path.stat().st_size
    if not force and object_exists(client, bucket, key):
        print(f"[skip] {path.name}", flush=True)
        return {
            "status": "skipped",
            "local_path": str(path),
            "r2_key": key,
            "public_url": public_url(key),
            "size_bytes": size_bytes,
        }

    content_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    print(f"[upload] {path.name} ({size_bytes / 1024 / 1024:.1f} MB)", flush=True)
    client.upload_file(
        str(path),
        bucket,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    return {
        "status": "uploaded",
        "local_path": str(path),
        "r2_key": key,
        "public_url": public_url(key),
        "size_bytes": size_bytes,
    }


def write_r2_manifest(
    batch_dir: Path,
    channel_id: str,
    batch_id: str,
    group: str,
    results: list[dict],
) -> Path:
    manifest_path = batch_dir / f"r2_manifest_{channel_id}_{batch_id}_{group}.json"
    payload = {
        "channel_id": channel_id,
        "batch_id": batch_id,
        "group": group,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(results),
        "items": results,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a dated stock batch Source folder to R2.")
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--channel-id", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--group", default=DEFAULT_GROUP)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env(args.env_file)
    batch_dir = args.batch_dir.expanduser().resolve()
    files = iter_video_files(batch_dir)
    if not files:
        raise RuntimeError(f"No MP4 files found in {batch_dir / 'Source'}")

    local_manifest = load_local_manifest(batch_dir)
    local_by_id = manifest_items_by_video_id(local_manifest)

    print(f"Batch folder: {batch_dir}", flush=True)
    print(f"Files: {len(files)}", flush=True)
    print(f"Channel: {args.channel_id}", flush=True)
    print(f"Batch: {args.batch_id}", flush=True)

    bucket = require_env("R2_BUCKET_NAME")
    client = None if args.dry_run else r2_client()
    results: list[dict] = []

    for path in files:
        key = build_key(args.channel_id, args.batch_id, args.group, path)
        video_id = video_id_from_filename(path)
        local_metadata = local_by_id.get(video_id or "", {})
        if args.dry_run:
            print(f"[dry-run] {path.name} -> {key}", flush=True)
            result = {
                "status": "dry_run",
                "local_path": str(path),
                "r2_key": key,
                "public_url": public_url(key),
                "size_bytes": path.stat().st_size,
            }
        else:
            result = upload_file(client, bucket, path, key, args.force)

        result.update({
            "video_id": video_id,
            "guest": local_metadata.get("guest"),
            "title": local_metadata.get("title"),
            "source_url": local_metadata.get("url"),
        })
        results.append(result)

    manifest_path = write_r2_manifest(batch_dir, args.channel_id, args.batch_id, args.group, results)
    uploaded = sum(1 for item in results if item["status"] == "uploaded")
    skipped = sum(1 for item in results if item["status"] == "skipped")
    print(f"Uploaded: {uploaded}, skipped: {skipped}, manifest: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
