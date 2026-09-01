"""
Give existing clips the poster frames the pipeline now produces for new ones.

S08 and S10 generate thumbnails from the local file before upload, but every
clip cut before that change has none — and its 16:9 landscape source is already
gone from R2, deleted by the orchestrator once captions succeeded. The captioned
vertical file survives, so that is what these frames come from.

Usage:
    python tools/backfill_clip_thumbnails.py --dry-run
    python tools/backfill_clip_thumbnails.py --channels otherside_cast,theyellow_cast
"""

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from app.services.supabase_client import get_client            # noqa: E402
from app.services.thumbnails import make_thumbnail, VERTICAL_WIDTH  # noqa: E402


def fetch_pending(channels: list[str]) -> list[dict]:
    rows = (
        get_client().table("clips")
        .select("id,job_id,clip_index,video_captioned_path,channel_id")
        .in_("channel_id", channels)
        .is_("thumbnail_path", "null")
        .not_.is_("video_captioned_path", "null")
        .execute()
    )
    return rows.data or []


def process(clip: dict) -> tuple[str, str | None]:
    key = f"thumbnails/{clip['job_id']}/{clip.get('clip_index') or 0}_vertical.jpg"
    url = make_thumbnail(clip["video_captioned_path"], key, width=VERTICAL_WIDTH)
    if url:
        get_client().table("clips").update({"thumbnail_path": url}).eq("id", clip["id"]).execute()
    return clip["id"], url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channels", default="otherside_cast,theyellow_cast")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    channels = [c.strip() for c in args.channels.split(",") if c.strip()]
    pending = fetch_pending(channels)
    print(f"{len(pending)} clips need a thumbnail across {channels}")

    if args.dry_run or not pending:
        for c in pending[:5]:
            print(f"  would do {c['id']} -> thumbnails/{c['job_id']}/{c.get('clip_index') or 0}_vertical.jpg")
        return 0

    done = failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(process, c) for c in pending]
        for fut in as_completed(futures):
            try:
                _, url = fut.result()
            except Exception as e:
                print(f"  error: {e}")
                failed += 1
                continue
            if url:
                done += 1
            else:
                failed += 1
            if (done + failed) % 25 == 0:
                print(f"  {done + failed}/{len(pending)} processed ({failed} failed)")

    print(f"Done. {done} written, {failed} failed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
