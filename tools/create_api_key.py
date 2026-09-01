"""
Mint an API key for the standalone step endpoints.

The raw key is printed once and never stored — only its sha256 goes to the
database. If it is lost, revoke the row and mint another.

    python tools/create_api_key.py --name "ekrem-laptop" --channel otherside_cast
    python tools/create_api_key.py --list
    python tools/create_api_key.py --revoke <id>
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from app.middleware.api_key import generate_key            # noqa: E402
from app.services.supabase_client import get_client        # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name")
    ap.add_argument("--channel", default=None, help="channel the key acts as; decides the watermark")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--revoke", metavar="ID")
    args = ap.parse_args()

    c = get_client()

    if args.list:
        rows = c.table("api_keys").select("id,name,channel_id,created_at,last_used_at,revoked_at").execute().data or []
        for r in rows:
            state = "revoked" if r["revoked_at"] else "active"
            used = r["last_used_at"] or "never used"
            print(f"{r['id']}  {state:<8} {r['name']:<20} {r['channel_id'] or '(no channel)':<18} {used}")
        return 0

    if args.revoke:
        c.table("api_keys").update({"revoked_at": "now()"}).eq("id", args.revoke).execute()
        print(f"revoked {args.revoke}")
        return 0

    if not args.name:
        ap.error("--name is required when creating a key")

    raw, key_hash = generate_key()
    c.table("api_keys").insert({
        "key_hash": key_hash,
        "name": args.name,
        "channel_id": args.channel,
    }).execute()

    print("\nKey created. This is the only time it is shown:\n")
    print(f"  {raw}\n")
    print(f"  name    {args.name}")
    print(f"  channel {args.channel or '(none — output will be unmarked)'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
