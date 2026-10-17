"""Authentication endpoints (Registration, Login, User profile)."""

import re
import uuid
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from ...auth import AuthenticatedUser, create_access_token, get_current_user
from ...logger import logger

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory storage for demonstration/testing when local Supabase instance is offline
_USERS_DB: Dict[str, dict] = {}

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")


import hashlib
import os
import secrets

def _hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with random 16-byte salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}:{key.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored salt:key using constant-time comparison."""
    try:
        parts = stored_hash.split(":")
        if len(parts) != 2:
            return False
        salt = bytes.fromhex(parts[0])
        expected_key = bytes.fromhex(parts[1])
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return secrets.compare_digest(key, expected_key)
    except Exception:
        return False


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        if not EMAIL_REGEX.match(v):
            raise ValueError("Invalid email format")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(v) > 128:
            raise ValueError("Password cannot exceed 128 characters")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        if not EMAIL_REGEX.match(v):
            raise ValueError("Invalid email format")
        return v.lower()


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """Register a new user and return JWT access token."""
    email_key = request.email.lower()
    if email_key in _USERS_DB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    user_id = str(uuid.uuid4())
    _USERS_DB[email_key] = {
        "id": user_id,
        "email": email_key,
        "password_hash": _hash_password(request.password),
        "full_name": request.full_name,
    }
    logger.info(f"Registered user {user_id} with email {email_key}")

    token = create_access_token(user_id=user_id, email=email_key)
    return AuthResponse(access_token=token, user_id=user_id, email=email_key)


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Authenticate existing user credentials and return JWT access token."""
    email_key = request.email.lower()
    user = _USERS_DB.get(email_key)
    if not user or not _verify_password(request.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user_id=user["id"], email=email_key)
    return AuthResponse(access_token=token, user_id=user["id"], email=email_key)


@router.get("/me")
async def get_me(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Protected route: retrieves current verified user from server-side JWT."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
    }
