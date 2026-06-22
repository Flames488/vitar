"""
Vitar v5 - Security (HARDENED)
- Uses bcrypt library directly (passlib has a bug with bcrypt>=4.x)
- sha256 pre-hash prevents 72-byte truncation
- Eager-loads subscription on get_current_clinic
"""

import hashlib
import base64
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(auto_error=False)


def _extract_token(request: Request, credentials) -> str | None:
    """
    v11: Accept token from httpOnly cookie (preferred) OR Authorization header.
    Cookie takes precedence; header fallback keeps API clients working.
    """
    # 1. httpOnly cookie (browser clients)
    from app.core.cookie_auth import get_access_token_from_cookie
    token = get_access_token_from_cookie(request)
    if token:
        return token
    # 2. Bearer header (API clients, mobile apps)
    if credentials:
        return credentials.credentials
    return None


def _prehash(password: str) -> bytes:
    """sha256+base64 → 44 bytes — prevents bcrypt 72-byte truncation."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc).replace(tzinfo=None) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def generate_secure_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


# Keep 'security' name for backward compat with existing imports
security = security_scheme


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
):
    from app.models.models import User

    # v11: accept token from httpOnly cookie OR Authorization header
    token = _extract_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def get_current_clinic(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Eager-loads subscription so trial_guard works without lazy-load errors."""
    from app.models.models import Clinic

    clinic = (
        db.query(Clinic)
        .options(joinedload(Clinic.subscription))
        .filter(Clinic.owner_id == current_user.id, Clinic.is_active == True)
        .first()
    )
    if not clinic:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return clinic


def get_current_superadmin(
    current_user=Depends(get_current_user),
):
    """
    v12 — Admin Dashboard: protects every /admin/* endpoint.

    Server-side enforcement only — the frontend route guard is a UX nicety,
    never the actual security boundary. Raises 403 (not 404) so a regular
    authenticated user gets a clear "not allowed" rather than a misleading
    "not found".
    """
    if not getattr(current_user, "is_superadmin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required",
        )
    return current_user
