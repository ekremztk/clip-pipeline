"""Download and organize SpeedyCast source videos.

Creates:
  ~/Source Videos/
    A Series/
      Clipped/
    B Series/
      Clipped/
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse


DEFAULT_MANIFEST = Path("tools/speedy_source_videos_initial.json")
DEFAULT_ROOT = Path.home() / "Source Videos"
FORMAT = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"


def safe_name(value: str) -> str:
    value = re.sub(r"[/:*?\"<>|]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        return parsed.path.strip("/")
    query_id = parse_qs(parsed.query).get("v", [""])[0]
    return query_id or safe_name(url)[-12:]


def load_manifest(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def create_series_dirs(root: Path, series: str) -> dict[str, Path]:
    base = root / safe_name(series)
    paths = {
        "base": base,
        "clipped": base / "Clipped",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def create_readme(root: Path) -> None:
    readme = root / "README.txt"
    if readme.exists():
        return
    readme.write_text(
        "SpeedyCast source archive\n"
        "\n"
        "Folder layout:\n"
        "- A Series: original A-series source videos for upload to pipeline\n"
        "- A Series/Clipped: pipeline clips produced from A-series sources\n"
        "- B Series: original B-series source videos for upload to pipeline\n"
        "- B Series/Clipped: pipeline clips produced from B-series sources\n"
        "\n"
        "This folder is ignored by git.\n",
        encoding="utf-8",
    )


def iter_entries(manifest: list[dict], only_series: str | None) -> list[dict]:
    entries: list[dict] = []
    for item in manifest:
        series = item["series"]
        if only_series and series != only_series:
            continue
        guest = item["guest"]
        for url in item.get("urls", []):
            entries.append({"series": series, "guest": guest, "url": url, "manual": False})
        for url in item.get("manual_upscaled", []):
            entries.append({"series": series, "guest": guest, "url": url, "manual": True})
    return entries


def download_video(entry: dict, root: Path, archive: Path, include_manual: bool) -> None:
    paths = create_series_dirs(root, entry["series"])

    if entry["manual"] and not include_manual:
        marker = paths["base"] / "manual_upscaled_needed.txt"
        with marker.open("a", encoding="utf-8") as handle:
            handle.write(f"{entry['guest']} — {video_id(entry['url'])} — {entry['url']}\n")
        print(f"[skip manual] {entry['guest']} — {entry['url']}")
        return

    output_template = str(paths["base"] / "%(upload_date>%Y-%m-%d)s - %(title).160B [%(id)s].%(ext)s")
    cmd = [
        "yt-dlp",
        "-f",
        FORMAT,
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
    print(f"[download] {entry['series']} / {entry['guest']} — {entry['url']}")
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download SpeedyCast source videos into production folders.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--series", choices=["A Series", "B Series"], default=None)
    parser.add_argument("--create-folders-only", action="store_true")
    parser.add_argument("--include-manual-upscaled", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    args.root.mkdir(parents=True, exist_ok=True)
    create_readme(args.root)
    archive = args.root / "_downloaded_archive.txt"

    for item in manifest:
        if args.series and item["series"] != args.series:
            continue
        create_series_dirs(args.root, item["series"])

    if args.create_folders_only:
        print(f"Created folder structure under: {args.root}")
        return

    entries = iter_entries(manifest, args.series)
    print(f"Entries to process: {len(entries)}")
    failures: list[dict] = []
    for entry in entries:
        try:
            download_video(entry, args.root, archive, args.include_manual_upscaled)
        except subprocess.CalledProcessError as exc:
            print(f"[failed] {entry['series']} / {entry['guest']} — {entry['url']} ({exc})")
            failures.append(entry)

    if failures:
        print("\nFailed downloads:")
        for failure in failures:
            print(f"- {failure['series']} / {failure['guest']}: {failure['url']}")
        raise SystemExit(1)

    print("Download batch complete.")


if __name__ == "__main__":
    main()
