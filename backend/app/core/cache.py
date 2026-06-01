"""
Vitar v5.2 - Redis Cache Layer
Provides a simple, robust cache for expensive queries and API responses.
All operations fail-open: if Redis is down, the app continues uncached.

Usage:
    from app.core.cache import cache

    # In an endpoint or service:
    data = await cache.get("clinic:stats:abc123")
    if data is None:
        data = expensive_query(...)
        await cache.set("clinic:stats:abc123", data, ttl=300)

    # Decorator pattern (sync functions):
    @cache.cached(key_prefix="geo", ttl=3600)
    def get_country_from_ip(ip: str): ...

    # Invalidation:
    await cache.delete("clinic:stats:abc123")
    await cache.delete_pattern("clinic:stats:*")
"""

import json
import logging
import hashlib
import functools
from typing import Any, Optional, Callable
from datetime import timedelta

logger = logging.getLogger(__name__)

# Default TTLs (seconds)
TTL_SHORT  = 60        # 1 minute — volatile data (queue depths, active workers)
TTL_MEDIUM = 300       # 5 minutes — clinic/doctor stats
TTL_LONG   = 3600      # 1 hour — geo lookups, pricing, config
TTL_DAY    = 86_400    # 24 hours — rarely-changing reference data


class RedisCache:
    """
    Thread-safe Redis cache with JSON serialisation.
    Singleton: import `cache` below, never instantiate directly.
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import redis as redis_lib
                from app.core.config import settings
                url = settings.REDIS_URL
                # Sentinel support: redis-sentinel://host1:port,host2:port/master_name/db
                # This allows docker-compose.redis-ha.yml to be used without code changes.
                if url.startswith("redis-sentinel://"):
                    from redis.sentinel import Sentinel
                    # Parse: redis-sentinel://host1:port1,host2:port2/master_name/db
                    stripped = url[len("redis-sentinel://"):]
                    parts = stripped.split("/")
                    hosts_str = parts[0]
                    master_name = parts[1] if len(parts) > 1 else "mymaster"
                    db = int(parts[2]) if len(parts) > 2 else 0
                    sentinels = [
                        (h.split(":")[0], int(h.split(":")[1]))
                        for h in hosts_str.split(",")
                    ]
                    sentinel = Sentinel(
                        sentinels,
                        socket_timeout=1,
                        socket_connect_timeout=1,
                    )
                    self._client = sentinel.master_for(
                        master_name,
                        db=db,
                        decode_responses=True,
                        retry_on_timeout=True,
                    )
                else:
                    self._client = redis_lib.from_url(
                        url,
                        decode_responses=True,
                        socket_connect_timeout=1,
                        socket_timeout=1,
                        retry_on_timeout=True,
                    )
                self._client.ping()
                logger.debug("Cache: Redis client connected")
            except Exception as exc:
                logger.warning(f"Cache: Redis unavailable ({exc}) — running uncached")
                self._client = None
        return self._client

    # ── Core operations ────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        """Return cached value or None if missing/Redis down."""
        r = self._get_client()
        if r is None:
            return None
        try:
            raw = r.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as exc:
            logger.warning(f"Cache.get({key!r}) failed: {exc}")
            return None

    def set(self, key: str, value: Any, ttl: int = TTL_MEDIUM) -> bool:
        """Store value with TTL. Returns True on success."""
        r = self._get_client()
        if r is None:
            return False
        try:
            r.set(key, json.dumps(value, default=str), ex=ttl)
            return True
        except Exception as exc:
            logger.warning(f"Cache.set({key!r}) failed: {exc}")
            return False

    def delete(self, key: str) -> bool:
        r = self._get_client()
        if r is None:
            return False
        try:
            r.delete(key)
            return True
        except Exception as exc:
            logger.warning(f"Cache.delete({key!r}) failed: {exc}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern. Returns count deleted."""
        r = self._get_client()
        if r is None:
            return 0
        try:
            keys = r.keys(pattern)
            if keys:
                return r.delete(*keys)
            return 0
        except Exception as exc:
            logger.warning(f"Cache.delete_pattern({pattern!r}) failed: {exc}")
            return 0

    def incr(self, key: str, ttl: int = TTL_SHORT) -> Optional[int]:
        """Atomic increment. Creates key at 1 if missing."""
        r = self._get_client()
        if r is None:
            return None
        try:
            count = r.incr(key)
            if count == 1:
                r.expire(key, ttl)
            return count
        except Exception as exc:
            logger.warning(f"Cache.incr({key!r}) failed: {exc}")
            return None

    def get_or_set(self, key: str, factory: Callable, ttl: int = TTL_MEDIUM) -> Any:
        """
        Get from cache; call factory() on miss and cache the result.
        Factory must be a synchronous callable.
        """
        value = self.get(key)
        if value is not None:
            return value
        value = factory()
        if value is not None:
            self.set(key, value, ttl=ttl)
        return value

    # ── Decorator ─────────────────────────────────────────────────────────────

    def cached(self, key_prefix: str, ttl: int = TTL_MEDIUM, key_fn: Optional[Callable] = None):
        """
        Decorator for sync functions.

            @cache.cached(key_prefix="geo_country", ttl=TTL_LONG)
            def resolve_country(ip: str) -> str:
                return slow_geo_lookup(ip)
        """
        def decorator(fn: Callable):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                if key_fn:
                    cache_key = key_fn(*args, **kwargs)
                else:
                    raw = f"{key_prefix}:{args}:{sorted(kwargs.items())}"
                    cache_key = f"{key_prefix}:{hashlib.md5(raw.encode()).hexdigest()}"

                result = self.get(cache_key)
                if result is not None:
                    return result
                result = fn(*args, **kwargs)
                if result is not None:
                    self.set(cache_key, result, ttl=ttl)
                return result
            return wrapper
        return decorator

    # ── Health ─────────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        r = self._get_client()
        if r is None:
            return False
        try:
            return r.ping()
        except Exception:
            return False

    def info(self) -> dict:
        """Return memory usage and hit-rate stats for monitoring."""
        r = self._get_client()
        if r is None:
            return {"status": "unavailable"}
        try:
            info = r.info("stats", "memory")
            return {
                "status": "ok",
                "used_memory_human": info.get("used_memory_human"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "evicted_keys": info.get("evicted_keys", 0),
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}


# ── Singleton instance ─────────────────────────────────────────────────────────
cache = RedisCache()


# ── Convenience key builders ───────────────────────────────────────────────────

def clinic_stats_key(clinic_id: str) -> str:
    return f"cache:clinic:stats:{clinic_id}"

def doctor_list_key(clinic_id: str) -> str:
    return f"cache:clinic:doctors:{clinic_id}"

def patient_list_key(clinic_id: str, page: int = 1) -> str:
    return f"cache:clinic:patients:{clinic_id}:p{page}"

def geo_country_key(ip: str) -> str:
    return f"cache:geo:country:{hashlib.md5(ip.encode()).hexdigest()}"

def exchange_rate_key(from_cur: str, to_cur: str) -> str:
    return f"cache:fx:{from_cur}:{to_cur}"

def analytics_key(clinic_id: str, period: str) -> str:
    return f"cache:analytics:{clinic_id}:{period}"
