import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Header
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from app.config import settings
from app.database import db

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7


def _get_jwt_secret() -> str:
    if not settings.jwt_secret:
        secret = secrets.token_hex(32)
        settings.jwt_secret = secret
        logger.warning("AUDIARR_JWT_SECRET not set. Generated random secret: %s", secret)
    return settings.jwt_secret


def _get_admin_api_key() -> str:
    if not settings.admin_api_key:
        key = secrets.token_hex(16)
        settings.admin_api_key = key
        logger.warning("AUDIARR_ADMIN_API_KEY not set. Generated random key: %s", key)
    return settings.admin_api_key


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, _get_jwt_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def get_token_from_header(authorization: str = Header(None)) -> str:
    if not authorization:
        raise HTTPException(HTTP_401_UNAUTHORIZED, "Not authenticated")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(HTTP_401_UNAUTHORIZED, "Invalid authorization header")
    return token


async def get_current_user(token: str = Depends(get_token_from_header)) -> dict:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    username = payload.get("sub")
    if not username:
        raise HTTPException(HTTP_401_UNAUTHORIZED, "Invalid token payload")
    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(HTTP_401_UNAUTHORIZED, "User not found")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(HTTP_403_FORBIDDEN, "Admin access required")
    return user


def verify_admin_api_key(authorization: str = Header(None)) -> bool:
    if not authorization:
        raise HTTPException(HTTP_401_UNAUTHORIZED, "Admin API key required")
    scheme, _, key = authorization.partition(" ")
    if key != _get_admin_api_key():
        raise HTTPException(HTTP_403_FORBIDDEN, "Invalid admin API key")
    return True
