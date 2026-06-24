"""
Role detection helpers for admin vs client users.
Uses psycopg2 directly for performance (single query, no ORM overhead).
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import Depends, HTTPException, status

from app.middleware.auth import get_current_user
from app.services.supabase_client import get_db_url


def _db_connect():
    db_url = get_db_url()
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)


def is_admin_user(user_id: str) -> bool:
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM admin_users WHERE user_id = %s::uuid LIMIT 1",
                    (user_id,),
                )
                return cur.fetchone() is not None
    except Exception as e:
        print(f"[Roles] admin check error: {e}")
        return False


def is_client_user(user_id: str) -> bool:
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM client_accounts WHERE user_id = %s::uuid LIMIT 1",
                    (user_id,),
                )
                return cur.fetchone() is not None
    except Exception as e:
        print(f"[Roles] client check error: {e}")
        return False


def get_user_role(user_id: str) -> dict:
    """
    Returns role info: {is_admin, is_client, client_account, credit_info}
    """
    result = {"is_admin": False, "is_client": False, "client_account": None, "credit_info": None}
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM admin_users WHERE user_id = %s::uuid LIMIT 1",
                    (user_id,),
                )
                if cur.fetchone():
                    result["is_admin"] = True
                    return result

                cur.execute(
                    """
                    SELECT ca.display_name, ca.allowed_domains, ca.max_channels,
                           uc.balance, uc.is_locked, uc.consecutive_failures,
                           uc.max_concurrent_jobs, uc.storage_cap_bytes, uc.clip_retention_days
                    FROM client_accounts ca
                    LEFT JOIN user_credits uc ON uc.user_id = ca.user_id
                    WHERE ca.user_id = %s::uuid
                    LIMIT 1
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if row:
                    result["is_client"] = True
                    result["client_account"] = {
                        "display_name": row["display_name"],
                        "allowed_domains": row["allowed_domains"],
                        "max_channels": row["max_channels"],
                    }
                    result["credit_info"] = {
                        "balance": row["balance"] or 0,
                        "is_locked": row["is_locked"] or False,
                        "consecutive_failures": row["consecutive_failures"] or 0,
                        "max_concurrent_jobs": row["max_concurrent_jobs"] or 2,
                        "storage_cap_bytes": row["storage_cap_bytes"] or 10737418240,
                        "clip_retention_days": row["clip_retention_days"] or 30,
                    }
    except Exception as e:
        print(f"[Roles] get_user_role error: {e}")
    return result


def require_client(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency — raises 403 if user is not a registered client."""
    user_id = current_user.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authenticated user",
        )

    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ca.display_name, ca.allowed_domains, ca.max_channels,
                           uc.balance, uc.is_locked
                    FROM client_accounts ca
                    LEFT JOIN user_credits uc ON uc.user_id = ca.user_id
                    WHERE ca.user_id = %s::uuid
                    LIMIT 1
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
    except Exception as e:
        print(f"[Roles] require_client error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Role check unavailable",
        ) from e

    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client access required",
        )

    return {
        "id": current_user["id"],
        "email": current_user.get("email"),
        "display_name": row["display_name"],
        "is_locked": row["is_locked"] or False,
        "balance": row["balance"] or 0,
    }
