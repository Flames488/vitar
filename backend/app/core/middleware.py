"""
Vitar v5 - Middleware (HARDENED)
- Per-route rate limits (auth endpoints stricter)
- Structured request logging
- Security response headers
- Request ID tracking
"""

import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.logging import get_logger
from app.core.observability import record_request_latency

logger = get_logger("vitar.http")

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis as redis_lib
            from app.core.config import settings
            _redis_client = redis_lib.from_url(
                settings.REDIS_URL, decode_responses=True,
                socket_connect_timeout=1, socket_timeout=1,
            )
            _redis_client.ping()
        except Exception as e:
            logger.warning(f"Rate limiter Redis unavailable: {e}")
            _redis_client = None
    return _redis_client


# Per-prefix rate limits: (max_requests, window_seconds)
RATE_RULES = [
    ("/api/v1/auth/login",    10,  60),   # 10 login attempts per minute per IP
    ("/api/v1/auth/register", 5,   60),   # 5 registrations per minute
    ("/api/v1/auth/forgot",   5,  300),   # 5 password resets per 5 minutes
    ("/api/v1/auth/",        20,  60),    # all other auth endpoints
    ("/api/v1/ai/chat",      10,  60),    # AI chat: expensive, 10 req/min
    ("/api/v1/ai/",          30,  60),    # AI endpoints: 30 req/min per IP
    ("/api/v1/webhooks/",   500,  60),    # Webhooks need high limit
    ("/api/",               200,  60),    # Default API
]


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        r = _get_redis()
        if not r:
            return await call_next(request)

        ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
              or (request.client.host if request.client else "unknown"))

        path = request.url.path
        limit, window = 200, 60
        for prefix, lim, win in RATE_RULES:
            if path.startswith(prefix):
                limit, window = lim, win
                break

        # Normalise path: strip UUIDs/numeric IDs so /appointments/uuid-1 and
        # /appointments/uuid-2 share the same rate-limit bucket instead of creating
        # a unique Redis key per resource (avoids Redis key explosion).
        import re as _re
        _bucket_path = _re.sub(
            r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "/{id}", path, flags=_re.IGNORECASE
        )
        _bucket_path = _re.sub(r"/[0-9]+", "/{id}", _bucket_path)
        key = f"rl:{ip}:{_bucket_path}:{int(time.time() // window)}"
        try:
            count = r.incr(key)
            if count == 1:
                r.expire(key, window)
            if count > limit:
                logger.warning("Rate limit exceeded", extra={"ip": ip, "path": path, "count": count})
                return JSONResponse(
                    status_code=429,
                    content={"error": "Too many requests", "retry_after": window},
                    headers={"Retry-After": str(window)},
                )
        except Exception as e:
            logger.warning(f"Rate limit error: {e}")

        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                f"Middleware caught unhandled exception",
                exc_info=exc,
                extra={"method": request.method, "path": request.url.path,
                       "duration_ms": duration_ms, "request_id": request_id},
            )
            return JSONResponse(
                status_code=500,
                content={"error": "internal", "request_id": request_id},
            )
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
              or (request.client.host if request.client else "unknown"))

        if request.url.path not in ("/health", "/"):
            log_fn = logger.warning if response.status_code >= 400 else logger.info
            log_fn(
                f"{request.method} {request.url.path}",
                extra={"method": request.method, "path": request.url.path,
                       "status": response.status_code, "duration_ms": duration_ms,
                       "ip": ip, "request_id": request_id},
            )
            # SLA latency tracking — fires Slack alert if p95 breaches threshold
            record_request_latency(duration_ms, request.url.path)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cache-Control"] = "no-store"
        # HSTS: enforce HTTPS for 1 year, include subdomains
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "frame-ancestors 'none'"
        )
        return response
