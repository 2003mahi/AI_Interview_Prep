"""Supabase Authentication & JWT verification module."""

import time
from typing import Optional
import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .config import settings
from .logger import logger

security = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    id: str
    email: Optional[str] = None
    role: str = "authenticated"


def create_access_token(user_id: str, email: Optional[str] = None, expires_in: int = 3600) -> str:
    """Helper to generate Supabase-compatible JWT for testing and auth service."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> AuthenticatedUser:
    """
    Verify Supabase JWT token from Authorization header.
    Never trusts client-supplied user IDs; retrieves the user ID directly from token payload.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError as e:
        logger.warning(f"Invalid token error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or malformed authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing or invalid user identity",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Enforce safe audience if aud claim is provided
    aud = payload.get("aud")
    if aud and aud != "authenticated":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token audience: authenticated audience required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role = payload.get("role", "authenticated")
    if role != "authenticated":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized token role: authenticated user required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        id=user_id.strip(),
        email=payload.get("email"),
        role=role,
    )
