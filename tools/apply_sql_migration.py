"""Apply a backend SQL migration using DATABASE_URL from backend/.env."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a SQL migration.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path("backend/.env"))
    args = parser.parse_args()

    load_env(args.env_file)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured")

    sql = args.path.read_text(encoding="utf-8")
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print(f"Applied migration: {args.path}")


if __name__ == "__main__":
    main()
