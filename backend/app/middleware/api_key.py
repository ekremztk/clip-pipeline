"""
API-key authentication for the standalone step endpoints.

These are called with curl rather than from the app, so there is no Supabase
session to check. A key is 32 random bytes shown once at creation; only its
sha256 is stored, so a leaked database yields no working keys. A plain hash is
the right choice for a value with that much entropy — there is nothing here to
brute-force, unlike a password.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import Header, HTTPException

from app.services.supabase_client import get_client

KEY_PREFIX = "pk_"


def generate_key() -> tuple[str, str]:
    """Return (raw_key, key_hash). The raw key is never stored."""
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, hash_key(raw)


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def require_api_key(x_prognot_key: Optional[str] = Header(default=None)) -> dict:
    """
    FastAPI dependency. Returns the key row, so a handler can read the channel
    the key acts as. Raises 401 for anything missing, unknown or revoked.
    """
    if not x_prognot_key:
        raise HTTPException(status_code=401, detail="X-Prognot-Key header is required")

    supabase = get_client()
    try:
        res = (
            supabase.table("api_keys").select("*")
            .eq("key_hash", hash_key(x_prognot_key.strip()))
            .is_("revoked_at", "null")
            .execute()
        )
    except Exception as e:
        print(f"[ApiKey] lookup failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    if not res.data:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")

    row = res.data[0]
    # Best-effort: a key that works should not stop working because the
    # bookkeeping write failed.
    try:
        supabase.table("api_keys").update(
            {"last_used_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", row["id"]).execute()
    except Exception as e:
        print(f"[ApiKey] last_used_at update failed: {e}")

    return row
