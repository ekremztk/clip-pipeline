"""
One-shot R2 cleanup.

Only two prefixes are permanent:
  - captions/      → S10 final output, referenced by clips.video_captioned_path
  - voice-library/ → Voice fingerprint audio samples

Everything else is transient and safe to purge. This script removes:
  - source_videos/ (Modal inputs, 3-4 GB each, the main leak)
  - reframe/       (S09 podcast intermediates)
  - gaming-reframe/(S09 gaming intermediates)
  - debug/         (diagnostic overlays from reframe pipeline)
  - gaming-debug/  (diagnostic overlays from gaming pipeline)
  - reframe-uploads/ (manual uploads from /api/reframe debug endpoint)
  - <uuid>/        (S08 landscape exports — redundant, clips use captions/)

Usage:
    cd backend
    python -m scripts.cleanup_r2 --dry-run   # list what would be deleted
    python -m scripts.cleanup_r2             # actually delete

Run ONCE to free ~14 GB of accumulated garbage. Ongoing cleanup is handled
automatically by orchestrator.py (pipeline-end cleanup) and the TTL scheduler.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from app.config import settings
from app.services.r2_client import get_r2_client


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_FIXED_TRANSIENT_PREFIXES = [
    "source_videos/",
    "reframe/",
    "gaming-reframe/",
    "debug/",
    "gaming-debug/",
    "reframe-uploads/",
]

_KEEP_PREFIXES = ["captions/", "voice-library/"]


def _top_level(key: str) -> str:
    return key.split("/", 1)[0]


def _iter_all_keys(bucket: str):
    s3 = get_r2_client()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []) or []:
            yield obj["Key"], obj.get("Size", 0)


def _batch_delete(bucket: str, keys: list[str]) -> int:
    if not keys:
        return 0
    s3 = get_r2_client()
    total = 0
    for i in range(0, len(keys), 1000):
        chunk = keys[i : i + 1000]
        s3.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
        )
        total += len(chunk)
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="list only, no deletes")
    args = ap.parse_args()

    bucket = settings.R2_BUCKET_NAME
    if not bucket:
        print("R2_BUCKET_NAME not set")
        return 1

    print(f"Scanning bucket: {bucket}")
    if args.dry_run:
        print("(dry run — nothing will be deleted)")

    by_prefix: dict[str, list[str]] = defaultdict(list)
    size_by_prefix: dict[str, int] = defaultdict(int)
    total_objects = 0
    total_bytes = 0

    for key, size in _iter_all_keys(bucket):
        total_objects += 1
        total_bytes += size

        # Keep rules — skip permanent prefixes entirely
        if any(key.startswith(p) for p in _KEEP_PREFIXES):
            by_prefix["__KEPT__"].append(key)
            size_by_prefix["__KEPT__"] += size
            continue

        # Fixed transient prefixes
        matched = False
        for pref in _FIXED_TRANSIENT_PREFIXES:
            if key.startswith(pref):
                by_prefix[pref].append(key)
                size_by_prefix[pref] += size
                matched = True
                break
        if matched:
            continue

        # Top-level UUID → S08 landscape exports (<job_id>/<filename>)
        top = _top_level(key)
        if _UUID_RE.match(top):
            by_prefix["<job_id>/"].append(key)
            size_by_prefix["<job_id>/"] += size
            continue

        by_prefix["__UNKNOWN__"].append(key)
        size_by_prefix["__UNKNOWN__"] += size

    def _mb(n: int) -> str:
        return f"{n / 1024 / 1024:.1f} MB"

    print()
    print(f"Total scanned: {total_objects} objects, {_mb(total_bytes)}")
    print()
    print("Breakdown:")
    for pref in sorted(by_prefix.keys()):
        print(
            f"  {pref:<24} {len(by_prefix[pref]):>6} objects  {_mb(size_by_prefix[pref]):>12}"
        )

    delete_candidates: list[str] = []
    for pref, keys in by_prefix.items():
        if pref in ("__KEPT__", "__UNKNOWN__"):
            continue
        delete_candidates.extend(keys)

    if by_prefix.get("__UNKNOWN__"):
        print()
        print("⚠ Unknown top-level keys (NOT deleting — review manually):")
        for k in by_prefix["__UNKNOWN__"][:20]:
            print(f"    {k}")
        if len(by_prefix["__UNKNOWN__"]) > 20:
            print(f"    ... and {len(by_prefix['__UNKNOWN__']) - 20} more")

    print()
    print(f"→ Would delete {len(delete_candidates)} objects")

    if args.dry_run or not delete_candidates:
        return 0

    confirm = input("Type DELETE to proceed: ").strip()
    if confirm != "DELETE":
        print("Aborted.")
        return 1

    deleted = _batch_delete(bucket, delete_candidates)
    print(f"Deleted {deleted} objects.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
