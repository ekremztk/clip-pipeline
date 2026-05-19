"""Scan YouTube source channels and insert guest-matched source videos."""

import argparse
import os
import re
import time

from dotenv import load_dotenv
from supabase import create_client

import yt_dlp


DEFAULT_POOL_PREFIX = "speedy_cast"
DEFAULT_MIN_DURATION_SECONDS = 180
DEFAULT_MAX_DURATION_SECONDS = 1200
DEFAULT_LIMIT_PER_GUEST_CHANNEL = 10
DEFAULT_MATCH_MODE = "guest-like"

GUEST_ALIASES = {
    "Dwayne Johnson": ["The Rock"],
    "Robert Downey Jr.": ["Robert Downey Jr", "RDJ"],
    "Conan O'Brien": ["Conan OBrien"],
    "Samuel L. Jackson": ["Samuel L Jackson"],
}


load_dotenv("backend/.env")
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


class QuietYtdlpLogger:
    def debug(self, msg):
        return

    def warning(self, msg):
        return

    def error(self, msg):
        return


def table_name(pool_prefix, suffix):
    return f"{pool_prefix}_{suffix}"


def get_evergreen_guests(pool_prefix):
    result = (
        supabase.table(table_name(pool_prefix, "guests"))
        .select("id, guest_name, score")
        .eq("category", "evergreen")
        .eq("active", True)
        .order("score", desc=True)
        .execute()
    )
    return result.data


def get_source_channels(pool_prefix):
    result = (
        supabase.table(table_name(pool_prefix, "source_channels"))
        .select("channel_name, handle, youtube_channel_id")
        .eq("active", True)
        .execute()
    )
    return result.data


def channel_videos_url(handle):
    normalized = handle.strip().rstrip("/")
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return f"{normalized}/videos"
    return f"https://www.youtube.com/{normalized.lstrip('/')}/videos"


def fetch_channel_videos_flat(handle, max_videos):
    """Phase 1: fast flat scan, only titles and IDs."""
    url = channel_videos_url(handle)
    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "daterange": yt_dlp.utils.DateRange("20220101", None),
        "logger": QuietYtdlpLogger(),
    }
    if max_videos > 0:
        ydl_opts["playlistend"] = max_videos

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=False)
        if not result:
            return []
        entries = result.get("entries", []) or []

    videos = []
    for entry in entries:
        if not entry:
            continue
        videos.append({
            "video_id": entry.get("id"),
            "title": entry.get("title", ""),
        })

    return videos


def fetch_video_details(video_id):
    """Phase 2: fetch full metadata for a single video."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "skip_download": True,
        "logger": QuietYtdlpLogger(),
        "socket_timeout": 12,
        "retries": 1,
        "fragment_retries": 1,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            return {
                "view_count": int(info.get("view_count") or 0),
                "duration": int(info.get("duration") or 0),
                "upload_date": info.get("upload_date"),
                "thumbnail": info.get("thumbnail"),
            }
    except Exception as e:
        print(f"      Failed to fetch details for {video_id}: {e}")
        return None


def aliases_for_guest(guest_name):
    return [guest_name, *GUEST_ALIASES.get(guest_name, [])]


def _topic_only_alias_context(title, alias):
    normalized = re.sub(r"\s+", " ", title or "").strip()
    alias_pattern = re.escape(alias).replace(r"\ ", r"\s+")
    topic_patterns = [
        rf"\bby\s+{alias_pattern}\b",
        rf"\bwith\s+{alias_pattern}\b",
        rf"\bon\s+{alias_pattern}(?:'s)?\b",
        rf"\babout\s+{alias_pattern}\b",
        rf"\bfor\s+{alias_pattern}\b",
        rf"\bfrom\s+{alias_pattern}\b",
        rf"\bbefore\s+{alias_pattern}\b",
        rf"\bafter\s+{alias_pattern}\b",
    ]
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in topic_patterns)


def _guest_like_alias_context(title, alias):
    normalized = re.sub(r"\s+", " ", title or "").strip()
    alias_pattern = re.escape(alias).replace(r"\ ", r"\s+")
    prefix_pattern = re.compile(
        rf"^(?:why\s+)?{alias_pattern}(?:\b|'s\b)",
        re.IGNORECASE,
    )
    if prefix_pattern.search(normalized):
        return True

    list_pattern = re.compile(
        rf"^[^:|]{{0,90}}\b(?:and\s+)?{alias_pattern}\s+"
        r"(?:talk|talks|play|plays|share|shares|reveal|reveals|explain|explains|react|reacts)\b",
        re.IGNORECASE,
    )
    if list_pattern.search(normalized):
        return True

    return False


def match_guest_in_title(title, guest_name, match_mode=DEFAULT_MATCH_MODE):
    for alias in aliases_for_guest(guest_name):
        escaped = re.escape(alias).replace(r"\ ", r"\s+")
        pattern = re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)
        if pattern.search(title or ""):
            if match_mode == "guest-like":
                if _topic_only_alias_context(title, alias):
                    continue
                if not _guest_like_alias_context(title, alias):
                    continue
            return alias
    return None


def format_upload_date(date_str):
    if not date_str or len(date_str) != 8:
        return None
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"


def get_existing_video_ids(pool_prefix):
    result = supabase.table(table_name(pool_prefix, "source_videos")).select("video_id").execute()
    return {row["video_id"] for row in result.data}


def get_existing_guest_channel_counts(pool_prefix):
    result = (
        supabase.table(table_name(pool_prefix, "source_videos"))
        .select("guest_id, source_handle")
        .execute()
    )
    counts = {}
    for row in result.data:
        key = (row["guest_id"], row["source_handle"])
        counts[key] = counts.get(key, 0) + 1
    return counts


def should_keep_duration(duration, min_duration, max_duration):
    return min_duration <= duration <= max_duration


def main():
    parser = argparse.ArgumentParser(description="Scan source channels for a channel-specific guest pool.")
    parser.add_argument("--pool-prefix", default=DEFAULT_POOL_PREFIX)
    parser.add_argument(
        "--max-videos-per-channel",
        type=int,
        default=0,
        help="Optional flat-scan cap for debugging. 0 scans all channel uploads.",
    )
    parser.add_argument("--min-duration", type=int, default=DEFAULT_MIN_DURATION_SECONDS)
    parser.add_argument("--max-duration", type=int, default=DEFAULT_MAX_DURATION_SECONDS)
    parser.add_argument("--limit-per-guest-channel", type=int, default=DEFAULT_LIMIT_PER_GUEST_CHANNEL)
    parser.add_argument("--match-mode", choices=["guest-like", "loose"], default=DEFAULT_MATCH_MODE)
    parser.add_argument("--priority-a-limit-per-channel", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--priority-b-limit-per-channel", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    guests = get_evergreen_guests(args.pool_prefix)
    channels = get_source_channels(args.pool_prefix)
    existing_ids = get_existing_video_ids(args.pool_prefix)
    existing_guest_channel_counts = get_existing_guest_channel_counts(args.pool_prefix)
    videos_table = table_name(args.pool_prefix, "source_videos")

    print(f"Pool prefix: {args.pool_prefix}")
    print(f"Evergreen guests: {[g['guest_name'] for g in guests]}")
    print(f"Source channels: {[c['handle'] for c in channels]}")
    print(f"Flat scan cap: {args.max_videos_per_channel if args.max_videos_per_channel > 0 else 'all'}")
    print(f"Duration filter: {args.min_duration}s-{args.max_duration}s")
    print(f"Per guest/channel limit: top {args.limit_per_guest_channel} by views")
    print(f"Match mode: {args.match_mode}")
    print(f"Already in DB: {len(existing_ids)} videos")
    print("---")

    guest_map = {g["guest_name"]: g for g in guests}
    total_inserted = 0

    for channel in channels:
        handle = channel["handle"]
        channel_name = channel["channel_name"]
        print(f"\nScanning {channel_name} ({handle})...")

        # Phase 1: fast flat scan
        videos = fetch_channel_videos_flat(handle, args.max_videos_per_channel)
        print(f"  Found {len(videos)} videos (flat scan)")

        # Find title matches
        matched_videos = []
        for video in videos:
            if video["video_id"] in existing_ids:
                continue
            for guest_name, guest in guest_map.items():
                matched_alias = match_guest_in_title(video["title"], guest_name, args.match_mode)
                if matched_alias:
                    matched_videos.append({
                        **video,
                        "guest_name": guest_name,
                        "guest_id": guest["id"],
                        "matched_alias": matched_alias,
                        "guest_score": int(guest.get("score") or 0),
                    })
                    break

        print(f"  Title matches: {len(matched_videos)}")

        # Phase 2: fetch full details only for matches, then keep top videos by views.
        detailed_matches = []
        skipped_no_details = 0
        skipped_by_duration = 0
        existing_by_guest = {
            guest["id"]: existing_guest_channel_counts.get((guest["id"], handle), 0)
            for guest in guests
        }
        for index, mv in enumerate(matched_videos, start=1):
            if index == 1 or index % 10 == 0:
                print(f"  Fetching details: {index}/{len(matched_videos)}")

            details = fetch_video_details(mv["video_id"])
            if not details:
                skipped_no_details += 1
                continue

            if not should_keep_duration(details["duration"], args.min_duration, args.max_duration):
                skipped_by_duration += 1
                continue

            detailed_matches.append({
                **mv,
                **details,
            })

            if args.sleep:
                time.sleep(args.sleep)

        detailed_matches.sort(key=lambda item: int(item.get("view_count") or 0), reverse=True)

        matches = 0
        skipped_by_guest_limit = 0
        written_by_guest = dict(existing_by_guest)
        for mv in detailed_matches:
            if written_by_guest.get(mv["guest_id"], 0) >= args.limit_per_guest_channel:
                skipped_by_guest_limit += 1
                continue

            row = {
                "guest_id": mv["guest_id"],
                "video_id": mv["video_id"],
                "title": mv["title"],
                "source_channel": channel_name,
                "source_handle": handle,
                "view_count": mv["view_count"],
                "duration_seconds": mv["duration"],
                "upload_date": format_upload_date(mv["upload_date"]),
                "thumbnail_url": mv.get("thumbnail"),
            }

            try:
                if not args.dry_run:
                    supabase.table(videos_table).insert(row).execute()
                existing_ids.add(mv["video_id"])
                written_by_guest[mv["guest_id"]] = written_by_guest.get(mv["guest_id"], 0) + 1
                existing_guest_channel_counts[(mv["guest_id"], handle)] = written_by_guest[mv["guest_id"]]
                matches += 1
                mode = "dry" if args.dry_run else "db"
                print(
                    f"    + [{mode}] {mv['guest_name']} "
                    f"({mv['matched_alias']}) | {mv['duration']}s | "
                    f"{mv['view_count']:,} views | {mv['title'][:70]}"
                )
            except Exception as e:
                if "duplicate" in str(e).lower():
                    pass
                else:
                    print(f"    ERROR: {e}")
        total_inserted += matches
        print(f"  Inserted: {matches}")
        if skipped_by_guest_limit:
            print(f"  Skipped by guest/channel DB-write limit: {skipped_by_guest_limit}")
        if skipped_no_details:
            print(f"  Skipped without details: {skipped_no_details}")
        if skipped_by_duration:
            print(f"  Skipped by duration: {skipped_by_duration}")
        if args.sleep:
            time.sleep(args.sleep)

    print(f"\n--- Done. Total new videos inserted: {total_inserted} ---")


if __name__ == "__main__":
    main()
