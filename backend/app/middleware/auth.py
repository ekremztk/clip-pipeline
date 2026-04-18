import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.supabase_client import get_client

_bearer = HTTPBearer(auto_error=False)

_DEV_USER_ID = os.getenv("TESTSPRITE_DEV_USER_ID")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """
    FastAPI dependency — extracts Bearer token and verifies it with Supabase.
    Returns {"id": user_id, "email": email} on success, raises 401 on failure.
    """
    # Dev bypass for TestSprite / local testing
    # Activates when TESTSPRITE_DEV_USER_ID is set and token is missing or not a real JWT
    _no_token = not credentials or not credentials.credentials
    _not_jwt = credentials and credentials.credentials and (
        credentials.credentials.count(".") != 2  # real JWTs have exactly 2 dots
    )
    if _DEV_USER_ID and (_no_token or _not_jwt):
        return {"id": _DEV_USER_ID, "email": "dev@testsprite.local"}

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        supabase = get_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Auth service unavailable",
            )

        response = supabase.auth.get_user(token)
        user = response.user

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return {"id": user.id, "email": user.email}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Auth] Token verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_token(token: str) -> dict | None:
    """
    Standalone helper for WebSocket auth (query param token).
    Returns user dict on success, None on failure (no exception).
    """
    try:
        supabase = get_client()
        if not supabase:
            return None

        response = supabase.auth.get_user(token)
        user = response.user

        if not user:
            return None

        return {"id": user.id, "email": user.email}

    except Exception as e:
        print(f"[Auth] WebSocket token verification error: {e}")
        return None
