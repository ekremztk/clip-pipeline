"""Run one Provision job from the terminal for smoke testing."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"


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


def infer_user_id(job_id: str, db_url: str) -> str:
    with psycopg2.connect(db_url, cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM provision_jobs WHERE id = %s LIMIT 1",
                (job_id,),
            )
            row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Provision job not found: {job_id}")
    return str(row["user_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Provision job locally.")
    parser.add_argument("job_id")
    parser.add_argument("--user-id")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--env-file", type=Path, default=BACKEND_DIR / ".env")
    args = parser.parse_args()

    load_env(args.env_file)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured")

    sys.path.insert(0, str(BACKEND_DIR))
    from app.provision.runner import run_provision_job

    user_id = args.user_id or infer_user_id(args.job_id, db_url)
    run_provision_job(args.job_id, user_id, limit=args.limit)
    print(f"Provision job finished: {args.job_id}")


if __name__ == "__main__":
    main()

