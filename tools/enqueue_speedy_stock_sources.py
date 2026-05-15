"""Enqueue SpeedyCast stock source videos from an R2 upload manifest."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from supabase import create_client


DEFAULT_ENV_FILE = Path("backend/.env")
DEFAULT_MANIFEST = Path.home() / "Source Videos" / "r2_manifest_speedy_cast_speedy_stock_20260516_a_series.json"

VIDEO_PEOPLE = {
    "rBKfRy0M-30": "Kevin Hart",
    "hEM5TKzUI8Q": "Kevin Hart",
    "kOYS9lX2pgg": "Ryan Reynolds",
    "8ARCrlFLu88": "Ryan Reynolds",
    "V9uHZ2uQ8YI": "Ryan Gosling",
    "_WtbbszO838": "Ryan Gosling",
    "9AXJSG6Qzcs": "Greg Davies",
    "zaCk5AKwmk0": "Greg Davies",
    "Mmtgt-xs5Gk": "Rowan Atkinson",
    "OQKAEjPIDNk": "Dwayne Johnson",
    "an1xCA5-UHw": "Dwayne Johnson",
    "4Y4YSpF6d6w": "Jack Black",
    "s68F_E9NfR0": "Jim Carrey",
    "RDwrdSBbyaY": "Jim Carrey",
    "2rJUAyilFmA": "Will Smith",
    "xdCTNas_YwQ": "Will Smith",
    "_u_TswLQ4ws": "Andrew Garfield",
    "nmMpwZrRLRQ": "Andrew Garfield",
    "X4puhH8kMwU": "Hugh Grant",
    "jIeyVA45TF4": "Hugh Grant",
    "8cVJvlix3EA": "Tom Holland",
    "e72pSP8lDLs": "Tom Holland",
    "b4M4I6FPiwU": "Robert Downey Jr.",
    "Z_2A5adT3FI": "Robert Downey Jr.",
    "AxG14lbL2Iw": "Conan O'Brien",
    "cq1er8IWz1U": "Conan O'Brien",
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


def video_id_from_name(name: str) -> str:
    match = re.search(r"\[([A-Za-z0-9_-]{11})\]", name)
    if not match:
        raise RuntimeError(f"Could not find YouTube id in filename: {name}")
    return match.group(1)


def title_from_name(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"\s*\[[A-Za-z0-9_-]{11}\]\s*$", "", stem)
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}\s+-\s+", "", stem)
    return re.sub(r"\s+", " ", stem).strip()


def get_channel_user_id(channel_id: str) -> str:
    client = create_client(require_env("SUPABASE_URL"), require_env("SUPABASE_SERVICE_KEY"))
    result = client.table("channels").select("id,user_id").eq("id", channel_id).single().execute()
    if not result.data:
        raise RuntimeError(f"Channel not found: {channel_id}")
    return result.data["user_id"]


def build_rows(manifest: dict, channel_id: str, user_id: str, args) -> list[tuple]:
    rows = []
    for item in manifest.get("items", []):
        filename = Path(item.get("local_path") or item["r2_key"]).name
        video_id = video_id_from_name(filename)
        main_person = VIDEO_PEOPLE.get(video_id)
        if not main_person:
            raise RuntimeError(f"No main_person mapping for video id {video_id}: {filename}")
        rows.append(
            (
                channel_id,
                user_id,
                args.batch_id,
                args.series,
                item["public_url"],
                item.get("r2_key"),
                title_from_name(filename),
                main_person,
                None,
                args.caption_template,
                "podcast",
                args.min_duration,
                args.max_duration,
                args.priority,
            )
        )
    return rows[: args.limit] if args.limit else rows


def enqueue(rows: list[tuple]) -> None:
    sql = """
        INSERT INTO stock_pipeline_queue (
            channel_id, user_id, batch_id, series, source_url, r2_key,
            video_title, main_person, target_guest, caption_template,
            reframe_content_type, clip_duration_min, clip_duration_max, priority
        ) VALUES %s
        ON CONFLICT (channel_id, batch_id, source_url)
        DO UPDATE SET
            series = EXCLUDED.series,
            r2_key = EXCLUDED.r2_key,
            video_title = EXCLUDED.video_title,
            main_person = EXCLUDED.main_person,
            target_guest = EXCLUDED.target_guest,
            caption_template = EXCLUDED.caption_template,
            reframe_content_type = EXCLUDED.reframe_content_type,
            clip_duration_min = EXCLUDED.clip_duration_min,
            clip_duration_max = EXCLUDED.clip_duration_max,
            priority = EXCLUDED.priority,
            updated_at = now()
        WHERE stock_pipeline_queue.status IN ('queued', 'failed')
    """
    with psycopg2.connect(require_env("DATABASE_URL")) as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enqueue SpeedyCast stock source videos.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--channel-id", default="speedy_cast")
    parser.add_argument("--batch-id", default="speedy_stock_20260516")
    parser.add_argument("--series", default="A Series")
    parser.add_argument("--caption-template", default="clean")
    parser.add_argument("--min-duration", type=int, default=10)
    parser.add_argument("--max-duration", type=int, default=60)
    parser.add_argument("--priority", type=int, default=100)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env(args.env_file)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    user_id = get_channel_user_id(args.channel_id)
    rows = build_rows(manifest, args.channel_id, user_id, args)

    print(f"Rows: {len(rows)}")
    for row in rows:
        print(f"- {row[7]} | {row[6]} | {row[5]}")

    if args.dry_run:
        return
    enqueue(rows)
    print("Enqueue complete.")


if __name__ == "__main__":
    main()
