"""Download and organize stock source videos from a title/link text file.

Creates:
  ~/Source Videos/{channel-name}/{batch-name}/
    Source/
    Clipped/
    _downloaded_archive.txt
    manifest.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse


DEFAULT_ROOT = Path.home() / "Source Videos"
DEFAULT_FORMAT = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"


def safe_name(value: str) -> str:
    value = value.replace("\ufeff", "")
    value = re.sub(r"[/:*?\"<>|]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        return parsed.path.strip("/")
    return parse_qs(parsed.query).get("v", [""])[0]


def is_youtube_url(line: str) -> bool:
    return "youtube.com/watch" in line or "youtu.be/" in line


def parse_selection_file(path: Path) -> list[dict]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()]
    entries: list[dict] = []
    current_guest = ""
    pending_title = ""

    for line in lines:
        if not line:
            continue
        if ";" in line:
            current_guest = safe_name(line.split(";", 1)[0])
            pending_title = ""
            continue
        if is_youtube_url(line):
            vid = video_id(line)
            if not vid:
                raise RuntimeError(f"Could not parse YouTube video id: {line}")
            entries.append(
                {
                    "guest": current_guest,
                    "title": pending_title or vid,
                    "url": line,
                    "video_id": vid,
                }
            )
            pending_title = ""
            continue
        pending_title = safe_name(line)

    return entries


def create_batch_dirs(root: Path, channel_name: str, batch_name: str) -> dict[str, Path]:
    base = root / safe_name(channel_name) / safe_name(batch_name)
    paths = {
        "base": base,
        "source": base / "Source",
        "clipped": base / "Clipped",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def write_manifest(paths: dict[str, Path], channel_name: str, batch_name: str, entries: list[dict]) -> Path:
    manifest_path = paths["base"] / "manifest.json"
    payload = {
        "channel_name": channel_name,
        "batch_name": batch_name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(entries),
        "items": entries,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def download_entry(entry: dict, paths: dict[str, Path], archive: Path, fmt: str) -> None:
    guest_prefix = safe_name(entry.get("guest") or "Unknown Guest")
    output_template = str(
        paths["source"]
        / f"{guest_prefix} - %(upload_date>%Y-%m-%d)s - %(title).150B [%(id)s].%(ext)s"
    )
    cmd = [
        "yt-dlp",
        "-f",
        fmt,
        "--remux-video",
        "mp4",
        "--no-playlist",
        "--no-progress",
        "--download-archive",
        str(archive),
        "-o",
        output_template,
        entry["url"],
    ]
    print(f"[download] {entry['guest']} — {entry['title']} — {entry['url']}", flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    default_batch_name = f"{datetime.now().strftime('%Y-%m-%d')} Stock Bench"
    parser = argparse.ArgumentParser(description="Download stock source videos into a dated batch folder.")
    parser.add_argument("--selection-file", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--channel-name", required=True)
    parser.add_argument("--batch-name", default=default_batch_name)
    parser.add_argument("--format", default=DEFAULT_FORMAT)
    parser.add_argument("--create-folders-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    entries = parse_selection_file(args.selection_file)
    paths = create_batch_dirs(args.root, args.channel_name, args.batch_name)
    archive = paths["base"] / "_downloaded_archive.txt"
    manifest_path = write_manifest(paths, args.channel_name, args.batch_name, entries)

    print(f"Batch folder: {paths['base']}", flush=True)
    print(f"Manifest: {manifest_path}", flush=True)
    print(f"Entries: {len(entries)}", flush=True)

    if args.create_folders_only:
        return

    failures: list[dict] = []
    for entry in entries:
        if args.dry_run:
            print(f"[dry-run] {entry['guest']} — {entry['title']} — {entry['url']}", flush=True)
            continue
        try:
            download_entry(entry, paths, archive, args.format)
        except subprocess.CalledProcessError as exc:
            print(f"[failed] {entry['guest']} — {entry['url']} ({exc})", flush=True)
            failures.append(entry)

    if failures:
        print("\nFailed downloads:", flush=True)
        for failure in failures:
            print(f"- {failure['guest']}: {failure['url']}", flush=True)
        raise SystemExit(1)

    print("Download batch complete.", flush=True)


if __name__ == "__main__":
    main()
