"""Upload local stock source videos to Cloudflare R2.

Default source folder:
  ~/Source Videos/A Series
  ~/Source Videos/B Series

Default R2 key layout:
  stock_sources/<channel>/<batch_id>/a_series/<filename>.mp4
  stock_sources/<channel>/<batch_id>/b_series/<filename>.mp4
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


DEFAULT_ROOT = Path.home() / "Source Videos"
DEFAULT_ENV_FILE = Path("backend/.env")
DEFAULT_CHANNEL = "speedy_cast"
SERIES_SLUGS = {
    "A Series": "a_series",
    "B Series": "b_series",
}


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
    name = filename.replace("\\", " ").replace("/", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return name


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


def iter_video_files(root: Path, series: str) -> list[Path]:
    series_dir = root / series
    if not series_dir.exists():
        raise RuntimeError(f"Series folder does not exist: {series_dir}")
    return sorted(
        path
        for path in series_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".mp4"
    )


def build_key(channel: str, batch_id: str, series: str, path: Path) -> str:
    series_slug = SERIES_SLUGS[series]
    return f"stock_sources/{channel}/{batch_id}/{series_slug}/{safe_key_name(path.name)}"


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


def write_manifest(root: Path, channel: str, batch_id: str, series: str, results: list[dict]) -> Path:
    manifest_path = root / f"r2_manifest_{channel}_{batch_id}_{SERIES_SLUGS[series]}.json"
    payload = {
        "channel": channel,
        "batch_id": batch_id,
        "series": series,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(results),
        "items": results,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main() -> None:
    default_batch = f"speedy_stock_{datetime.now().strftime('%Y%m%d')}"
    parser = argparse.ArgumentParser(description="Upload stock source videos to R2.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--channel", default=DEFAULT_CHANNEL)
    parser.add_argument("--batch-id", default=default_batch)
    parser.add_argument("--series", choices=sorted(SERIES_SLUGS), required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env(args.env_file)
    files = iter_video_files(args.root, args.series)
    if not files:
        raise RuntimeError(f"No MP4 files found in {args.root / args.series}")

    print(f"Files: {len(files)}", flush=True)
    print(f"Batch: {args.batch_id}", flush=True)
    print(f"Series: {args.series}", flush=True)

    bucket = require_env("R2_BUCKET_NAME")
    results: list[dict] = []
    client = None if args.dry_run else r2_client()

    for path in files:
        key = build_key(args.channel, args.batch_id, args.series, path)
        if args.dry_run:
            print(f"[dry-run] {path.name} -> {key}", flush=True)
            results.append(
                {
                    "status": "dry_run",
                    "local_path": str(path),
                    "r2_key": key,
                    "public_url": public_url(key),
                    "size_bytes": path.stat().st_size,
                }
            )
            continue
        results.append(upload_file(client, bucket, path, key, args.force))

    manifest_path = write_manifest(args.root, args.channel, args.batch_id, args.series, results)
    uploaded = sum(1 for item in results if item["status"] == "uploaded")
    skipped = sum(1 for item in results if item["status"] == "skipped")
    print(f"Uploaded: {uploaded}, skipped: {skipped}, manifest: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
