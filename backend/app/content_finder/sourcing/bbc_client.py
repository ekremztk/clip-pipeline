"""
BBC Programmes API client.

Uses a residential UK proxy (env BBC_PROXY_URL) because /programmes JSON
endpoints are UK-geofenced. Throttled to respect rate limits.

We only read public metadata — no stream URLs. Purely for indexing
episodes, synopses, thumbnails, and structured credits.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

BBC_BASE = "https://www.bbc.co.uk"
BBC_IMAGE_BASE = "https://ichef.bbci.co.uk/images/ic"
DEFAULT_THUMB_SIZE = "640x360"

# BBC PIDs are 8-10 lowercase alphanum, but paths like /articles, /schedules,
# /topics, /genres also match a loose regex — restrict to the known PID
# prefixes: b0xxxxxx (old catalogue) / m00xxxxx (modern) / p0xxxxx (images only).
_PID_RE = re.compile(r"/programmes/(b0[a-z0-9]{6,7}|m00[a-z0-9]{5,7})")


@dataclass
class BBCEpisodeMeta:
    pid: str
    title: str | None
    synopsis_short: str | None
    synopsis_medium: str | None
    synopsis_long: str | None
    thumbnail_url: str | None
    first_broadcast_at: str | None          # ISO 8601
    duration_sec: int | None
    series_num: int | None
    episode_num: int | None
    # Note: /programmes/{pid}/credits.json returns 404 across the catalogue
    # (verified 2026-04-29 against Graham Norton, Have I Got News for You,
    # and the brand root). Structured credits are not available — guest
    # extraction goes through synopsis_long → LLM parser + TVmaze cross-check.


class BBCClient:
    """Async client for BBC Programmes API with proxy + throttle."""

    def __init__(
        self,
        proxy_url: str | None = None,
        throttle_ms: int = 500,
        timeout_sec: float = 30.0,
    ):
        self.proxy_url = proxy_url or os.getenv("BBC_PROXY_URL")
        if not self.proxy_url:
            raise RuntimeError(
                "BBC_PROXY_URL is required. BBC Programmes JSON is UK-only."
            )
        self.throttle = throttle_ms / 1000.0
        self.timeout = timeout_sec
        self._last_request_at: float = 0.0
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BBCClient":
        self._client = httpx.AsyncClient(
            proxy=self.proxy_url,
            timeout=self.timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                ),
                "Accept": "application/json,text/html;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
            },
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def _throttled_get(self, url: str) -> httpx.Response:
        assert self._client is not None
        elapsed = asyncio.get_event_loop().time() - self._last_request_at
        if elapsed < self.throttle:
            await asyncio.sleep(self.throttle - elapsed)
        resp = await self._client.get(url)
        self._last_request_at = asyncio.get_event_loop().time()
        return resp

    # ── Discovery ────────────────────────────────────────────────

    async def list_series_pids(self, brand_pid: str) -> list[str]:
        """
        Crawl /programmes/{brand}/episodes/guide — this is the only
        brand-level page that lists ALL series (including off-iPlayer
        archival ones). Returns series PIDs (not episodes).

        The /episodes/player endpoint only shows iPlayer-streamable
        episodes (typically last 30 days) — useless for backfill.
        """
        url = f"{BBC_BASE}/programmes/{brand_pid}/episodes/guide"
        resp = await self._throttled_get(url)
        if resp.status_code != 200:
            return []
        candidates = [m for m in _PID_RE.findall(resp.text) if m != brand_pid]
        # De-dupe while preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for p in candidates:
            if p not in seen:
                seen.add(p)
                ordered.append(p)
        # Filter to series only (cheap JSON probe per candidate)
        series_pids: list[str] = []
        for pid in ordered:
            kind = await self._programme_type(pid)
            if kind == "series":
                series_pids.append(pid)
        return series_pids

    async def list_series_episodes(
        self, series_pid: str, brand_pid: str | None = None
    ) -> list[str]:
        """
        Crawl /programmes/{series}/episodes/guide?page=N for a given
        series. We use /episodes/guide (not /episodes/player) because
        /episodes/player only lists iPlayer-streamable episodes, which
        for archival series (pre-last-30-days) returns 0 results.

        Excludes the series PID itself and (if provided) the parent brand PID.
        """
        exclude = {series_pid}
        if brand_pid:
            exclude.add(brand_pid)

        pids: list[str] = []
        seen: set[str] = set()
        page = 1
        while True:
            url = f"{BBC_BASE}/programmes/{series_pid}/episodes/guide?page={page}"
            resp = await self._throttled_get(url)
            if resp.status_code != 200:
                break
            candidates = [p for p in _PID_RE.findall(resp.text) if p not in exclude]
            new = [p for p in candidates if p not in seen]
            if not new:
                break
            for p in new:
                seen.add(p)
                pids.append(p)
            page += 1
            if page > 50:  # safety cap
                break
        return pids

    async def list_episode_pids(self, brand_pid: str) -> list[str]:
        """
        Full crawl: brand → all series → all episodes of each series.
        Returns unique episode PIDs across the entire catalogue.
        """
        series_list = await self.list_series_pids(brand_pid)
        seen: set[str] = set()
        out: list[str] = []
        for s in series_list:
            eps = await self.list_series_episodes(s, brand_pid=brand_pid)
            for e in eps:
                if e not in seen:
                    seen.add(e)
                    out.append(e)
        return out

    async def _programme_type(self, pid: str) -> str | None:
        """Cheap JSON probe — returns 'brand' | 'series' | 'episode' | None."""
        url = f"{BBC_BASE}/programmes/{pid}.json"
        resp = await self._throttled_get(url)
        if resp.status_code != 200:
            return None
        try:
            return resp.json().get("programme", {}).get("type")
        except Exception:
            return None

    # ── Episode detail ──────────────────────────────────────────

    async def fetch_episode(self, pid: str) -> BBCEpisodeMeta | None:
        """Fetch /programmes/{pid}.json + /credits.json and assemble meta."""
        main_url = f"{BBC_BASE}/programmes/{pid}.json"
        resp = await self._throttled_get(main_url)
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except Exception:
            return None

        prog = data.get("programme", {})
        if prog.get("type") != "episode":
            return None

        # Thumbnail
        thumb_url = None
        img = prog.get("image") or {}
        img_pid = img.get("pid")
        if img_pid:
            thumb_url = f"{BBC_IMAGE_BASE}/{DEFAULT_THUMB_SIZE}/{img_pid}.jpg"

        # Broadcast + duration (from versions[])
        first_broadcast, duration = _extract_broadcast_and_duration(prog)

        # Series / episode numbers
        series_num, episode_num = _extract_series_episode(prog)

        return BBCEpisodeMeta(
            pid=pid,
            title=prog.get("title"),
            synopsis_short=prog.get("short_synopsis"),
            synopsis_medium=prog.get("medium_synopsis"),
            synopsis_long=prog.get("long_synopsis"),
            thumbnail_url=thumb_url,
            first_broadcast_at=first_broadcast,
            duration_sec=duration,
            series_num=series_num,
            episode_num=episode_num,
        )


# ── Helpers ────────────────────────────────────────────────────

def _extract_broadcast_and_duration(
    prog: dict[str, Any],
) -> tuple[str | None, int | None]:
    versions = prog.get("versions") or []
    duration = None
    first_broadcast = None
    for v in versions:
        if not duration and v.get("duration"):
            duration = int(v["duration"])
        broadcasts = v.get("broadcasts") or []
        for b in broadcasts:
            start = b.get("start")
            if start and (first_broadcast is None or start < first_broadcast):
                first_broadcast = start
    # Fallback — direct on programme
    if first_broadcast is None:
        first_broadcast = prog.get("first_broadcast_date")
    return first_broadcast, duration


def _extract_series_episode(
    prog: dict[str, Any],
) -> tuple[int | None, int | None]:
    """
    Series number: parse from the "Series N" title of the parent series node
    (NOT `position` — position is the series' index within the brand, not the
    series number itself; these can drift across specials/compilations).
    Episode number: prog.position first, then "Episode N" title fallback.
    """
    series_num: int | None = None

    parent = prog.get("parent")
    while parent:
        inner = parent.get("programme") or parent
        if inner.get("type") == "series":
            title = inner.get("title", "") or ""
            m = re.search(r"Series\s+(\d+)", title, re.IGNORECASE)
            if m:
                series_num = int(m.group(1))
                break
            # Last-resort: trust position only if the title had no "Series N"
            pos = inner.get("position")
            if pos:
                series_num = int(pos)
            break
        parent = inner.get("parent")

    episode_num = prog.get("position")
    if episode_num is not None:
        episode_num = int(episode_num)
    else:
        title = prog.get("title", "") or ""
        m = re.search(r"Episode\s+(\d+)", title, re.IGNORECASE)
        if m:
            episode_num = int(m.group(1))

    return series_num, episode_num
