"""
Vitar v5 - Idempotency Service
Prevents duplicate payment processing and webhook replay attacks.
Uses Redis for O(1) lookup with TTL-based expiry.
Falls back gracefully when Redis is unavailable.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from functools import wraps

logger = logging.getLogger(__name__)

# Redis client (lazy init to avoid import-time failures)
_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        try:
            import redis as redis_lib
            from app.core.config import settings
            _redis = redis_lib.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            _redis.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable for idempotency: {e}")
            _redis = None
    return _redis


# TTL for idempotency keys: 24 hours (covers delayed webhook re-delivery)
IDEMPOTENCY_TTL = 86_400  # seconds


class IdempotencyError(Exception):
    """Raised when a duplicate operation is detected."""
    pass


class DuplicatePaymentError(IdempotencyError):
    """Raised when a payment reference has already been processed."""
    pass


def _make_key(namespace: str, identifier: str) -> str:
    return f"idempotent:{namespace}:{hashlib.sha256(identifier.encode()).hexdigest()}"


def check_and_mark(namespace: str, identifier: str, ttl: int = IDEMPOTENCY_TTL) -> bool:
    """
    Atomically check-and-set an idempotency key.
    Returns True if this is a NEW (safe to process) operation.
    Returns False if this identifier was already processed (duplicate — skip).
    
    Uses SET NX (set if not exists) — atomic in Redis.
    Falls back to True (allow) when Redis is unavailable, logging a warning.
    """
    r = _get_redis()
    if r is None:
        logger.warning(f"Idempotency Redis unavailable — allowing {namespace}:{identifier[:16]}...")
        return True  # Fail open — don't block operations when Redis is down

    key = _make_key(namespace, identifier)
    try:
        result = r.set(key, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), nx=True, ex=ttl)
        return result is True  # None = key existed, True = newly set
    except Exception as e:
        logger.warning(f"Idempotency check failed: {e} — allowing operation")
        return True  # Fail open


def get_cached_result(namespace: str, identifier: str) -> Optional[Any]:
    """Retrieve a previously cached result for an idempotent operation."""
    r = _get_redis()
    if r is None:
        return None
    key = _make_key(namespace, identifier) + ":result"
    try:
        val = r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


def cache_result(namespace: str, identifier: str, result: Any, ttl: int = IDEMPOTENCY_TTL):
    """Cache the result of an idempotent operation for return on duplicate calls."""
    r = _get_redis()
    if r is None:
        return
    key = _make_key(namespace, identifier) + ":result"
    try:
        r.set(key, json.dumps(result, default=str), ex=ttl)
    except Exception as e:
        logger.warning(f"Failed to cache idempotency result: {e}")


def invalidate(namespace: str, identifier: str):
    """Remove an idempotency key (e.g., on confirmed failure, to allow retry)."""
    r = _get_redis()
    if r is None:
        return
    r.delete(_make_key(namespace, identifier))
    r.delete(_make_key(namespace, identifier) + ":result")


# ── Payment-specific helpers ───────────────────────────────────────────────────

def is_payment_processed(reference: str) -> bool:
    """Returns True if this payment reference was already processed."""
    return not check_and_mark("payment", reference)


def mark_payment_processed(reference: str):
    """Mark a payment reference as processed."""
    check_and_mark("payment", reference)


def is_webhook_processed(provider: str, event_id: str) -> bool:
    """Returns True if this webhook event was already handled."""
    return not check_and_mark("webhook", f"{provider}:{event_id}", ttl=3_600)


# ── Database-level idempotency check ──────────────────────────────────────────

def check_payment_reference_db(reference: str, db) -> bool:
    """
    Secondary check in DB (covers Redis failure window).
    Returns True if reference already exists in subscription_payments.
    """
    from app.models.models import SubscriptionPayment
    try:
        exists = db.query(SubscriptionPayment).filter(
            SubscriptionPayment.provider_reference == reference
        ).first()
        return exists is not None
    except Exception as e:
        logger.error(f"DB idempotency check failed: {e}")
        return False
