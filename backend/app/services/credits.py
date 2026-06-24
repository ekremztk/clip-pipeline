"""
Credit banking service — reserve/confirm/refund pattern with row-level locking.
Uses psycopg2 directly for SELECT ... FOR UPDATE support.
"""

import math
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from app.services.supabase_client import get_db_url


def _db_connect():
    db_url = get_db_url()
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)


def calculate_credits_needed(duration_seconds: float) -> int:
    """1 credit = 1 minute. Floor division, minimum 1."""
    return max(1, math.floor(duration_seconds / 60))


def get_balance(user_id: str) -> dict | None:
    """Returns credit info for a client user, or None if not a client."""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT balance, is_locked, locked_reason, consecutive_failures,
                           max_concurrent_jobs, storage_cap_bytes, clip_retention_days
                    FROM user_credits
                    WHERE user_id = %s::uuid
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return dict(row)
    except Exception as e:
        print(f"[Credits] get_balance error: {e}")
        return None


def check_concurrent_jobs(user_id: str) -> int:
    """Returns the number of currently active (queued/processing) jobs for this user."""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM jobs
                    WHERE user_id = %s::uuid
                    AND status IN ('queued', 'processing', 'analyzing', 'cutting')
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                return int(row["cnt"]) if row else 0
    except Exception as e:
        print(f"[Credits] check_concurrent_jobs error: {e}")
        return 0


def reserve_credits(user_id: str, job_id: str, amount: int) -> bool:
    """
    Atomically deduct credits from user balance.
    Uses SELECT ... FOR UPDATE to prevent race conditions.
    Returns True on success, False on insufficient balance or locked account.
    Raises on DB errors.
    """
    if amount <= 0:
        return True

    try:
        conn = _db_connect()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT balance, is_locked
                    FROM user_credits
                    WHERE user_id = %s::uuid
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return False

                if row["is_locked"]:
                    conn.rollback()
                    return False

                if row["balance"] < amount:
                    conn.rollback()
                    return False

                new_balance = row["balance"] - amount

                cur.execute(
                    """
                    UPDATE user_credits
                    SET balance = %s, updated_at = %s
                    WHERE user_id = %s::uuid
                    """,
                    (new_balance, datetime.now(timezone.utc), user_id),
                )

                cur.execute(
                    """
                    INSERT INTO credit_transactions (user_id, job_id, type, amount, balance_after, note)
                    VALUES (%s::uuid, %s::uuid, 'reserve', %s, %s, %s)
                    """,
                    (user_id, job_id, -amount, new_balance, f"Reserved {amount} credits for job"),
                )

                conn.commit()
                return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        print(f"[Credits] reserve_credits error: {e}")
        raise


def confirm_credits(user_id: str, job_id: str) -> None:
    """
    Mark a credit reservation as confirmed (job completed successfully).
    Resets consecutive_failures counter.
    """
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT balance FROM user_credits WHERE user_id = %s::uuid",
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    return

                cur.execute(
                    """
                    INSERT INTO credit_transactions (user_id, job_id, type, amount, balance_after, note)
                    VALUES (%s::uuid, %s::uuid, 'confirm', 0, %s, 'Job completed successfully')
                    """,
                    (user_id, job_id, row["balance"]),
                )

                cur.execute(
                    """
                    UPDATE user_credits
                    SET consecutive_failures = 0, updated_at = %s
                    WHERE user_id = %s::uuid
                    """,
                    (datetime.now(timezone.utc), user_id),
                )
                conn.commit()
    except Exception as e:
        print(f"[Credits] confirm_credits error: {e}")


def refund_credits(user_id: str, job_id: str, amount: int) -> dict:
    """
    Refund credits on job failure. Increments consecutive_failures.
    Returns {refunded, new_balance, is_locked, consecutive_failures}.
    """
    result = {"refunded": False, "new_balance": 0, "is_locked": False, "consecutive_failures": 0}

    if amount <= 0:
        return result

    try:
        conn = _db_connect()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT balance, consecutive_failures, is_locked
                    FROM user_credits
                    WHERE user_id = %s::uuid
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return result

                new_balance = row["balance"] + amount
                new_failures = row["consecutive_failures"] + 1
                should_lock = new_failures >= 3

                cur.execute(
                    """
                    UPDATE user_credits
                    SET balance = %s,
                        consecutive_failures = %s,
                        is_locked = %s,
                        locked_reason = %s,
                        updated_at = %s
                    WHERE user_id = %s::uuid
                    """,
                    (
                        new_balance,
                        new_failures,
                        should_lock,
                        f"Auto-locked after {new_failures} consecutive failures" if should_lock else row.get("locked_reason"),
                        datetime.now(timezone.utc),
                        user_id,
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO credit_transactions (user_id, job_id, type, amount, balance_after, note)
                    VALUES (%s::uuid, %s::uuid, 'refund', %s, %s, %s)
                    """,
                    (user_id, job_id, amount, new_balance, f"Refund: job failed (failure #{new_failures})"),
                )

                conn.commit()
                result["refunded"] = True
                result["new_balance"] = new_balance
                result["is_locked"] = should_lock
                result["consecutive_failures"] = new_failures
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        print(f"[Credits] refund_credits error: {e}")

    return result


def topup_credits(user_id: str, amount: int, admin_user_id: str, note: str = "") -> dict:
    """Admin topup. Returns {success, new_balance}."""
    result = {"success": False, "new_balance": 0}

    if amount <= 0:
        return result

    try:
        conn = _db_connect()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT balance FROM user_credits
                    WHERE user_id = %s::uuid
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return result

                new_balance = row["balance"] + amount

                cur.execute(
                    """
                    UPDATE user_credits
                    SET balance = %s, updated_at = %s
                    WHERE user_id = %s::uuid
                    """,
                    (new_balance, datetime.now(timezone.utc), user_id),
                )

                cur.execute(
                    """
                    INSERT INTO credit_transactions (user_id, type, amount, balance_after, note)
                    VALUES (%s::uuid, 'topup', %s, %s, %s)
                    """,
                    (user_id, amount, new_balance, note or f"Admin topup by {admin_user_id}"),
                )

                conn.commit()
                result["success"] = True
                result["new_balance"] = new_balance
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        print(f"[Credits] topup_credits error: {e}")

    return result


def get_storage_usage_bytes(user_id: str) -> int:
    """Get total storage used by client's clips (bytes). Estimates from clip count * average size if no size column."""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS clip_count
                    FROM clips c
                    JOIN jobs j ON c.job_id = j.id
                    WHERE j.user_id = %s::uuid
                    AND c.video_captioned_path IS NOT NULL
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                clip_count = int(row["clip_count"]) if row else 0
                # Estimate ~50MB per captioned clip (9:16, 30-60s, 1080p)
                return clip_count * 52_428_800
    except Exception as e:
        print(f"[Credits] get_storage_usage_bytes error: {e}")
        return 0


def get_transactions(user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """Get transaction history for a user."""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, job_id::text, type, amount, balance_after, note, created_at
                    FROM credit_transactions
                    WHERE user_id = %s::uuid
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, limit, offset),
                )
                rows = cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        print(f"[Credits] get_transactions error: {e}")
        return []
