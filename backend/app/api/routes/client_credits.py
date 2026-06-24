"""
Client-facing credit endpoints: balance, transactions, credit requests.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from app.middleware.auth import get_current_user
from app.middleware.roles import is_client_user, get_user_role
from app.services.credits import get_balance, get_transactions, get_storage_usage_bytes

router = APIRouter(prefix="/credits", tags=["credits"])


class CreditRequestBody(BaseModel):
    amount: int = Field(..., ge=10, le=5000)


@router.get("/balance")
async def credit_balance(current_user: dict = Depends(get_current_user)):
    """Returns credit balance and account status. Only accessible to client accounts."""
    user_id = current_user["id"]
    if not is_client_user(user_id):
        raise HTTPException(status_code=404, detail="Not a client account")

    info = get_balance(user_id)
    if not info:
        raise HTTPException(status_code=404, detail="Credit account not found")

    storage_used = get_storage_usage_bytes(user_id)
    return {
        "balance": info["balance"],
        "is_locked": info["is_locked"],
        "locked_reason": info.get("locked_reason"),
        "consecutive_failures": info["consecutive_failures"],
        "max_concurrent_jobs": info["max_concurrent_jobs"],
        "storage_used_bytes": storage_used,
        "storage_cap_bytes": info["storage_cap_bytes"],
        "clip_retention_days": info["clip_retention_days"],
    }


@router.get("/transactions")
async def credit_transactions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """Returns transaction history for the current client."""
    user_id = current_user["id"]
    if not is_client_user(user_id):
        raise HTTPException(status_code=404, detail="Not a client account")

    txns = get_transactions(user_id, limit=limit, offset=offset)
    return {"transactions": txns}


@router.post("/request")
async def request_credits(body: CreditRequestBody, current_user: dict = Depends(get_current_user)):
    """Submit a credit purchase request for admin approval."""
    user_id = current_user["id"]
    if not is_client_user(user_id):
        raise HTTPException(status_code=403, detail="Not a client account")

    import psycopg2
    from psycopg2.extras import RealDictCursor
    from app.services.supabase_client import get_db_url

    try:
        conn = psycopg2.connect(get_db_url(), cursor_factory=RealDictCursor)
        try:
            with conn.cursor() as cur:
                # Check for existing pending request
                cur.execute(
                    """
                    SELECT id FROM credit_requests
                    WHERE user_id = %s::uuid AND status = 'pending'
                    LIMIT 1
                    """,
                    (user_id,),
                )
                if cur.fetchone():
                    raise HTTPException(
                        status_code=409,
                        detail="You already have a pending credit request. Wait for admin approval.",
                    )

                cur.execute(
                    """
                    INSERT INTO credit_requests (user_id, amount_requested)
                    VALUES (%s::uuid, %s)
                    RETURNING id::text, amount_requested, status, created_at
                    """,
                    (user_id, body.amount),
                )
                row = cur.fetchone()
                conn.commit()

            # Notify admin
            try:
                from app.director.notifier import notify_custom
                notify_custom(
                    "Credit Request",
                    f"Client {current_user.get('email', user_id)} requested {body.amount} credits.",
                )
            except Exception:
                pass

            return {"request": dict(row), "message": "Credit request submitted. You will be notified when approved."}
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Credits] request_credits error: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit credit request")


@router.get("/role")
async def get_my_role(current_user: dict = Depends(get_current_user)):
    """Returns the user's role info. Used by frontend to determine access level."""
    role = get_user_role(current_user["id"])
    return {
        "is_admin": role["is_admin"],
        "is_client": role["is_client"],
        "credit_info": role.get("credit_info"),
    }
