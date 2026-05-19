"""Enqueue stock source videos from an R2 batch manifest."""

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


def get_channel_user_id(channel_id: str) -> str:
    client = create_client(require_env("SUPABASE_URL"), require_env("SUPABASE_SERVICE_KEY"))
    result = client.table("channels").select("id,user_id").eq("id", channel_id).single().execute()
    if not result.data:
        raise RuntimeError(f"Channel not found: {channel_id}")
    return result.data["user_id"]


def display_title(item: dict) -> str:
    local_path = item.get("local_path") or item.get("r2_key") or ""
    if local_path:
        stem = Path(local_path).stem
        stem = re.sub(r"\s*\[[A-Za-z0-9_-]{11}\]\s*$", "", stem)
        stem = re.sub(r"^.+?\s+-\s+\d{4}-\d{2}-\d{2}\s+-\s+", "", stem)
        stem = stem.replace("：", ":").replace("｜", "|").replace("＂", "\"")
        stem = re.sub(r"\s+", " ", stem).strip()
        if stem:
            return stem
    title = item.get("title")
    if title:
        return str(title).strip()
    return Path(local_path).stem.strip()


def main_person(item: dict) -> str:
    guest = item.get("guest")
    if guest:
        return str(guest).strip()
    raise RuntimeError(f"Manifest item is missing guest/main person: {item.get('r2_key')}")


def build_rows(manifest: dict, channel_id: str, user_id: str, args) -> list[tuple]:
    rows = []
    items = manifest.get("items") or []
    for item in items:
        public_url = str(item.get("public_url") or "").strip()
        r2_key = str(item.get("r2_key") or "").strip() or None
        title = display_title(item)
        person = main_person(item)
        if not public_url or not title or not person:
            raise RuntimeError(f"Invalid manifest item: {item}")
        rows.append(
            (
                channel_id,
                user_id,
                args.batch_id,
                args.series,
                public_url,
                r2_key,
                title,
                person,
                None,
                args.caption_template,
                args.reframe_content_type,
                args.min_duration,
                args.max_duration,
                args.priority,
            )
        )
    return rows[: args.limit] if args.limit else rows


def clear_queued(channel_id: str, user_id: str, batch_id: str) -> int:
    with psycopg2.connect(require_env("DATABASE_URL")) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM stock_pipeline_queue
                WHERE channel_id = %s
                  AND user_id = %s
                  AND batch_id = %s
                  AND status = 'queued'
                """,
                (channel_id, user_id, batch_id),
            )
            return int(cur.rowcount or 0)


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
    parser = argparse.ArgumentParser(description="Enqueue stock videos from an R2 batch manifest.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--channel-id", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--series", default="stock_bench")
    parser.add_argument("--caption-template", default="clean")
    parser.add_argument("--reframe-content-type", default="podcast")
    parser.add_argument("--min-duration", type=int, default=12)
    parser.add_argument("--max-duration", type=int, default=55)
    parser.add_argument("--priority", type=int, default=100)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--clear-queued", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env(args.env_file)
    manifest_path = args.manifest.expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    user_id = get_channel_user_id(args.channel_id)
    rows = build_rows(manifest, args.channel_id, user_id, args)

    print(f"Manifest: {manifest_path}")
    print(f"Rows: {len(rows)}")
    for row in rows:
        print(f"- {row[7]} | {row[6]} | {row[5]}")

    if args.dry_run:
        return

    cleared = clear_queued(args.channel_id, user_id, args.batch_id) if args.clear_queued else 0
    enqueue(rows)
    print(f"Enqueue complete. cleared={cleared}, inserted_or_updated={len(rows)}")


if __name__ == "__main__":
    main()
