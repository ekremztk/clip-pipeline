"""
BBC metadata scraper orchestrator.

For a given show_registry row:
  1. Enumerate all episode PIDs from the BBC brand page
  2. Fetch each episode's metadata (synopsis + thumbnail + credits)
  3. Upsert into source_videos with status='indexed'

Guest extraction is a separate step (guest_parser.py).
NZB matching is a separate step (nzb_matcher.py).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from app.content_finder.sourcing.bbc_client import BBCClient, BBCEpisodeMeta
from app.services.supabase_client import get_client


async def scrape_show(
    show_id: str,
    *,
    limit: int | None = None,
    skip_existing: bool = True,
) -> dict[str, Any]:
    """
    Scrape all episodes for a show. Returns a summary dict.

    Args:
        show_id: PK in show_registry (e.g. "graham_norton")
        limit: Cap number of episodes fetched (None = all)
        skip_existing: Skip PIDs already in source_videos (incremental crawl)
    """
    sb = get_client()
    if sb is None:
        raise RuntimeError("Supabase client unavailable")

    # Load show registry row
    show = (
        sb.table("show_registry")
        .select("id,display_name,bbc_brand_pid")
        .eq("id", show_id)
        .single()
        .execute()
    )
    show_row = show.data
    if not show_row or not show_row.get("bbc_brand_pid"):
        raise ValueError(f"show_registry row missing or has no bbc_brand_pid: {show_id}")

    brand_pid = show_row["bbc_brand_pid"]
    display_name = show_row["display_name"]
    print(f"[bbc_scraper] Starting scrape for {display_name} (brand={brand_pid})")

    async with BBCClient() as client:
        # Phase 1: enumerate PIDs
        all_pids = await client.list_episode_pids(brand_pid)
        print(f"[bbc_scraper] Discovered {len(all_pids)} episode PIDs")

        # Filter existing if incremental
        if skip_existing and all_pids:
            existing = (
                sb.table("source_videos")
                .select("pid")
                .eq("show_id", show_id)
                .in_("pid", all_pids)
                .execute()
            )
            existing_set = {r["pid"] for r in (existing.data or [])}
            pids_to_fetch = [p for p in all_pids if p not in existing_set]
            print(
                f"[bbc_scraper] Skipping {len(existing_set)} existing, "
                f"fetching {len(pids_to_fetch)} new"
            )
        else:
            pids_to_fetch = all_pids

        if limit is not None:
            pids_to_fetch = pids_to_fetch[:limit]

        # Phase 2: fetch details
        fetched = 0
        failed: list[str] = []
        for i, pid in enumerate(pids_to_fetch, 1):
            try:
                meta = await client.fetch_episode(pid)
            except Exception as e:
                print(f"[bbc_scraper] ERROR fetching {pid}: {e}")
                failed.append(pid)
                continue

            if meta is None:
                failed.append(pid)
                continue

            # Skip specials/compilations — no episode number, not clippable
            # material for our pipeline (Best-of, New Year's Eve, etc.)
            if meta.episode_num is None:
                continue

            # Skip compilation/best-of episodes — they reuse footage from
            # other episodes, no unique guest content to clip.
            if meta.title and "compilation" in meta.title.lower():
                continue

            _upsert_source_video(sb, show_id, meta)
            fetched += 1
            if i % 10 == 0:
                print(f"[bbc_scraper] Progress: {i}/{len(pids_to_fetch)}")

    # Update show_registry counters
    total = (
        sb.table("source_videos")
        .select("pid", count="exact")
        .eq("show_id", show_id)
        .execute()
    )
    episode_count = total.count or 0

    sb.table("show_registry").update(
        {
            "episode_count": episode_count,
            "last_scraped_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", show_id).execute()

    summary = {
        "show_id": show_id,
        "pids_discovered": len(all_pids),
        "pids_fetched": fetched,
        "pids_failed": failed,
        "total_in_db": episode_count,
    }
    print(f"[bbc_scraper] Done: {json.dumps(summary, indent=2)}")
    return summary


def _upsert_source_video(sb, show_id: str, meta: BBCEpisodeMeta) -> None:
    """
    Upsert a BBC episode meta row. Guests are populated by the separate
    guest_parser step — the scraper only inserts the raw metadata and
    leaves guests NULL for the parser to fill in.
    """
    row: dict[str, Any] = {
        "pid": meta.pid,
        "show_id": show_id,
        "series_num": meta.series_num,
        "episode_num": meta.episode_num,
        "title": meta.title,
        "synopsis_short": meta.synopsis_short,
        "synopsis_long": meta.synopsis_long,
        "thumbnail_url": meta.thumbnail_url,
        "first_broadcast_at": meta.first_broadcast_at,
        "duration_sec": meta.duration_sec,
        "status": "indexed",
    }
    sb.table("source_videos").upsert(row, on_conflict="pid").execute()


# ── CLI entrypoint for manual runs ───────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--show", default="graham_norton")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-skip", action="store_true")
    args = ap.parse_args()

    asyncio.run(
        scrape_show(
            args.show,
            limit=args.limit,
            skip_existing=not args.no_skip,
        )
    )
