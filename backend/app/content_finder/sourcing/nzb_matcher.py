"""
NZBgeek match worker.

For each indexed source_videos row, query NZBgeek (Newznab API) for the
show + series/episode, keep ONLY 1080p/2160p releases (720p or lower
breaks our reframe/caption pipeline — visually confirmed), pick the
best candidate, and write nzb_* columns.

NZBgeek Newznab endpoint:
    GET {NZBGEEK_API_URL}?t=tvsearch&apikey=...&q=...&season=N&ep=N&o=json

We then filter:
  - title contains 1080p or 2160p (and NOT 720p/480p/SD)
  - size is reasonable (> 300 MB — anything smaller is probably a sample)
Pick largest file among remaining (bigger = higher bitrate = cleaner source).

Sets:
  status='nzb_matched' + nzb_guid + nzb_title + nzb_size_mb + nzb_quality
or:
  status='unavailable' + unavailable_reason
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings


# Regex for quality tokens in release titles
_RE_2160P = re.compile(r"\b(2160p|4k|uhd)\b", re.IGNORECASE)
_RE_1080P = re.compile(r"\b1080p\b", re.IGNORECASE)
_RE_BAD_QUALITY = re.compile(
    r"\b(720p|480p|360p|sdtv|dvdrip|cam|ts|tc|workprint)\b", re.IGNORECASE
)

# Minimum file size to accept — anything smaller is likely a sample / subs-only
MIN_SIZE_MB = 300


@dataclass
class NZBCandidate:
    guid: str
    title: str
    size_bytes: int
    quality: str  # '1080p' | '2160p'

    @property
    def size_mb(self) -> int:
        return self.size_bytes // (1024 * 1024)


# ── Public entry ───────────────────────────────────────────────

async def match_show(
    show_id: str,
    *,
    limit: int | None = None,
    only_unmatched: bool = True,
) -> dict[str, Any]:
    """
    Match NZBs for all indexed episodes of a show. Returns summary.

    only_unmatched=True skips rows that already have nzb_guid or are
    marked unavailable.
    """
    from app.services.supabase_client import get_client

    if not settings.NZBGEEK_API_KEY:
        raise RuntimeError("NZBGEEK_API_KEY not configured")

    sb = get_client()
    if sb is None:
        raise RuntimeError("Supabase client unavailable")

    # Load show registry to get nzbgeek_query
    show = (
        sb.table("show_registry")
        .select("id,display_name,nzbgeek_query")
        .eq("id", show_id)
        .single()
        .execute()
    )
    show_row = show.data
    if not show_row or not show_row.get("nzbgeek_query"):
        raise ValueError(
            f"show_registry row missing or has no nzbgeek_query: {show_id}"
        )

    query_string = show_row["nzbgeek_query"]
    display_name = show_row["display_name"]
    print(f"[nzb_matcher] Matching for {display_name} (query='{query_string}')")

    # Load source_videos rows
    q = (
        sb.table("source_videos")
        .select("pid,series_num,episode_num,status,nzb_guid")
        .eq("show_id", show_id)
    )
    if only_unmatched:
        q = q.is_("nzb_guid", "null").neq("status", "unavailable")
    if limit is not None:
        q = q.limit(limit)
    rows = q.execute().data or []

    print(f"[nzb_matcher] {len(rows)} episodes to match")

    matched = 0
    unavailable = 0
    skipped = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, row in enumerate(rows, 1):
            pid = row["pid"]
            season = row.get("series_num")
            episode = row.get("episode_num")

            if season is None or episode is None:
                # Can't match without S/E — mark unavailable
                _write_unavailable(
                    sb, pid, "missing_series_or_episode_number"
                )
                skipped += 1
                continue

            try:
                candidate = await _find_best(
                    client, query_string, season, episode
                )
            except Exception as e:
                print(f"[nzb_matcher] ERROR for {pid} S{season}E{episode}: {e}")
                continue

            if candidate is None:
                _write_unavailable(sb, pid, "no_hd_release_found")
                unavailable += 1
            else:
                _write_matched(sb, pid, candidate)
                matched += 1

            if i % 10 == 0:
                print(
                    f"[nzb_matcher] Progress: {i}/{len(rows)} | "
                    f"matched={matched} unavail={unavailable} skip={skipped}"
                )

            # Gentle throttle — NZBgeek has rate limits
            await asyncio.sleep(0.5)

    summary = {
        "show_id": show_id,
        "processed": len(rows),
        "matched": matched,
        "unavailable": unavailable,
        "skipped": skipped,
    }
    print(f"[nzb_matcher] Done: {summary}")
    return summary


# ── NZBgeek query ──────────────────────────────────────────────

async def _find_best(
    client: httpx.AsyncClient,
    query: str,
    season: int,
    episode: int,
) -> NZBCandidate | None:
    """
    Call NZBgeek tvsearch and return the best HD candidate.
    Returns None if no 1080p/2160p release exists.
    """
    params = {
        "t": "tvsearch",
        "apikey": settings.NZBGEEK_API_KEY,
        "q": query,
        "season": str(season),
        "ep": str(episode),
        "o": "json",
    }
    resp = await client.get(settings.NZBGEEK_API_URL, params=params)
    if resp.status_code != 200:
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    items = _extract_items(data)
    if not items:
        return None

    candidates: list[NZBCandidate] = []
    for item in items:
        cand = _parse_item(item)
        if cand is not None:
            candidates.append(cand)

    if not candidates:
        return None

    # Prefer 2160p over 1080p; within quality, prefer larger file
    candidates.sort(
        key=lambda c: (0 if c.quality == "2160p" else 1, -c.size_bytes)
    )
    return candidates[0]


def _extract_items(data: Any) -> list[dict[str, Any]]:
    """
    Newznab JSON shape varies by provider. Handle both:
      { "channel": { "item": [...] } }
      { "item": [...] }
      []
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    channel = data.get("channel")
    if isinstance(channel, dict):
        item = channel.get("item")
        if isinstance(item, list):
            return item
        if isinstance(item, dict):
            return [item]
    item = data.get("item")
    if isinstance(item, list):
        return item
    if isinstance(item, dict):
        return [item]
    return []


def _parse_item(item: dict[str, Any]) -> NZBCandidate | None:
    """Parse a single Newznab item → NZBCandidate if it's 1080p+ and big enough."""
    title = item.get("title") or ""
    if not title:
        return None

    # Reject explicitly-bad quality tokens
    if _RE_BAD_QUALITY.search(title):
        return None

    if _RE_2160P.search(title):
        quality = "2160p"
    elif _RE_1080P.search(title):
        quality = "1080p"
    else:
        # No HD marker — skip (NZBgeek often lists SD/unspecified releases)
        return None

    # GUID — Newznab returns it as {"guid": {"_attributes": {"isPermaLink": ...}, "_value": "..."}}
    # or sometimes as a plain string. Handle both.
    guid = _extract_scalar(item.get("guid"))
    if not guid:
        return None

    size_bytes = _extract_size(item)
    if size_bytes < MIN_SIZE_MB * 1024 * 1024:
        return None

    return NZBCandidate(
        guid=guid,
        title=title,
        size_bytes=size_bytes,
        quality=quality,
    )


def _extract_scalar(val: Any) -> str | None:
    """Pull a scalar string out of an Newznab field that may be nested."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        # Some Newznab JSON libraries wrap scalars in {"#text": "..."} or {"_value": ...}
        for key in ("#text", "_value", "value", "url"):
            v = val.get(key)
            if isinstance(v, str):
                return v
    return None


def _extract_size(item: dict[str, Any]) -> int:
    """
    Size is often in <enclosure length="..."> or in attr.<size>.
    Try multiple paths to be defensive.
    """
    # Direct size field (Newznab extension)
    size = item.get("size")
    if isinstance(size, (int, str)):
        try:
            return int(size)
        except (ValueError, TypeError):
            pass

    # enclosure.length
    enclosure = item.get("enclosure")
    if isinstance(enclosure, dict):
        length = enclosure.get("length") or enclosure.get("@length")
        try:
            if length is not None:
                return int(length)
        except (ValueError, TypeError):
            pass

    # Newznab <attr name="size" value="..."/>
    attrs = item.get("attr") or item.get("newznab:attr") or []
    if isinstance(attrs, dict):
        attrs = [attrs]
    if isinstance(attrs, list):
        for a in attrs:
            if not isinstance(a, dict):
                continue
            name = a.get("name") or a.get("@name")
            if name == "size":
                val = a.get("value") or a.get("@value")
                try:
                    if val is not None:
                        return int(val)
                except (ValueError, TypeError):
                    continue

    return 0


# ── DB writers ─────────────────────────────────────────────────

def _write_matched(sb, pid: str, cand: NZBCandidate) -> None:
    sb.table("source_videos").update(
        {
            "nzb_guid": cand.guid,
            "nzb_title": cand.title,
            "nzb_size_mb": cand.size_mb,
            "nzb_quality": cand.quality,
            "nzb_matched_at": datetime.now(timezone.utc).isoformat(),
            "status": "nzb_matched",
            "unavailable_reason": None,
        }
    ).eq("pid", pid).execute()


def _write_unavailable(sb, pid: str, reason: str) -> None:
    sb.table("source_videos").update(
        {
            "status": "unavailable",
            "unavailable_reason": reason,
        }
    ).eq("pid", pid).execute()


# ── CLI ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--show", default="graham_norton")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--rematch", action="store_true",
                    help="Re-match rows that already have an nzb_guid")
    args = ap.parse_args()

    asyncio.run(
        match_show(
            args.show,
            limit=args.limit,
            only_unmatched=not args.rematch,
        )
    )
