"""
Vitar v11 — httpOnly Cookie Auth

Architecture:
  - access_token   → httpOnly cookie, 60-min expiry, SameSite=Strict
  - refresh_token  → httpOnly cookie, 30-day expiry, SameSite=Strict, path=/api/v1/auth/refresh
  - csrf_token     → plain (JS-readable) cookie + X-CSRF-Token header double-submit

CSRF exempt endpoints (no established session / external callers):
  - POST /api/v1/auth/login
  - POST /api/v1/auth/register
  - POST /api/v1/auth/refresh   ← FIX: was missing; caused all token refreshes to 403
  - POST /api/v1/auth/forgot-password
  - POST /api/v1/auth/reset-password
  - POST /api/v1/auth/logout    ← FIX: was missing; caused logout to 403 after cookie expiry
  - /api/v1/webhooks/           (external services)
  - /api/v1/booking/            (public patient-facing)
"""

import secrets
import logging
from typing import Optional
from fastapi import Request, HTTPException, status, Response
from app.core.config import settings

logger = logging.getLogger("vitar.cookie_auth")

ACCESS_COOKIE  = "vitar_access"
REFRESH_COOKIE = "vitar_refresh"
CSRF_COOKIE    = "vitar_csrf"


def _is_secure() -> bool:
    return settings.ENVIRONMENT == "production"


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    csrf_token: Optional[str] = None,
) -> str:
    if csrf_token is None:
        csrf_token = secrets.token_urlsafe(32)

    secure = _is_secure()

    response.set_cookie(
        key=ACCESS_COOKIE,
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth/refresh",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )
    return csrf_token


def clear_auth_cookies(response: Response) -> None:
    for cookie, path in [
        (ACCESS_COOKIE,  "/"),
        (REFRESH_COOKIE, "/api/v1/auth/refresh"),
        (CSRF_COOKIE,    "/"),
    ]:
        response.delete_cookie(
            key=cookie,
            path=path,
            httponly=(cookie != CSRF_COOKIE),
            secure=_is_secure(),
            samesite="strict",
        )


def get_access_token_from_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(ACCESS_COOKIE)


def get_refresh_token_from_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(REFRESH_COOKIE)


async def csrf_protect(request: Request) -> None:
    """
    FastAPI dependency: validates CSRF double-submit token on mutating requests.

    FIX: Added /api/v1/auth/refresh and /api/v1/auth/logout to exempt list.
    The refresh endpoint has no CSRF token yet (it's used to bootstrap a new one).
    The logout endpoint must succeed even when the CSRF cookie has expired.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    exempt_prefixes = (
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",       # FIX: bootstraps CSRF — no prior token available
        "/api/v1/auth/logout",        # FIX: must work even after CSRF cookie expiry
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
        "/api/v1/webhooks/",
        "/api/v1/booking/",
    )
    path = request.url.path
    if any(path.startswith(p) for p in exempt_prefixes):
        return

    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("X-CSRF-Token")

    if not cookie_token or not header_token:
        logger.warning(
            "CSRF token missing",
            extra={"path": path, "method": request.method,
                   "has_cookie": bool(cookie_token), "has_header": bool(header_token)},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid",
        )

    if not secrets.compare_digest(cookie_token, header_token):
        logger.warning("CSRF token mismatch", extra={"path": path, "method": request.method})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token mismatch",
        )
