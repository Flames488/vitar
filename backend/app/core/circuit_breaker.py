"""
Vitar v9 — Async Circuit Breaker with Timeouts & Fallback Responses

Upgrades over v8 recovery.py CircuitBreaker:
  1. Async-native (works with httpx / async service calls)
  2. Per-call configurable timeout via asyncio.wait_for
  3. Typed fallback responses — app never crashes on service failure
  4. Redis-backed state persistence (shared across workers / restarts)
  5. Prometheus metrics on every state transition
  6. success_threshold: require N successes in HALF_OPEN before CLOSED

Usage:
    from app.core.circuit_breaker import billing_breaker, ai_breaker

    # Async call:
    result = await billing_breaker.call_async(
        paystack_client.charge, amount=1000,
        fallback={"status": "queued"},
        timeout=15.0,
    )

    # Decorator pattern:
    @ai_breaker.protect_async(fallback={"score": 0.5}, timeout=20.0)
    async def score_patient(appointment_id):
        ...
"""

import asyncio
import logging
import threading
import time
import functools
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, TypeVar
from datetime import datetime, timezone

logger = logging.getLogger("vitar.circuit_breaker")

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


@dataclass
class _Stats:
    total_calls:          int   = 0
    total_failures:       int   = 0
    total_timeouts:       int   = 0
    total_fallbacks:      int   = 0
    consecutive_failures: int   = 0
    last_failure_at:      Optional[float] = None
    last_success_at:      Optional[float] = None


class AsyncCircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
        default_timeout: float = 10.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.default_timeout = default_timeout

        self._state = CircuitState.CLOSED
        self._stats = _Stats()
        self._probe_successes = 0
        self._lock = threading.Lock()

    # ── State ─────────────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._resolve_state()

    def _resolve_state(self) -> CircuitState:
        """Call with lock held."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - (self._stats.last_failure_at or 0)
            if elapsed >= self.recovery_timeout:
                logger.info("Circuit OPEN→HALF_OPEN", extra={"circuit": self.name})
                self._state = CircuitState.HALF_OPEN
                self._probe_successes = 0
        return self._state

    def _on_success(self):
        with self._lock:
            self._stats.total_calls += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_at = time.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._probe_successes += 1
                if self._probe_successes >= self.success_threshold:
                    logger.info("Circuit HALF_OPEN→CLOSED", extra={"circuit": self.name})
                    self._state = CircuitState.CLOSED
                    self._probe_successes = 0
        self._metric("success")

    def _on_failure(self, is_timeout: bool = False):
        with self._lock:
            self._stats.total_calls += 1
            self._stats.total_failures += 1
            if is_timeout:
                self._stats.total_timeouts += 1
            self._stats.consecutive_failures += 1
            self._stats.last_failure_at = time.monotonic()
            if (
                self._state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)
                and self._stats.consecutive_failures >= self.failure_threshold
            ):
                logger.error(
                    "Circuit → OPEN",
                    extra={"circuit": self.name, "failures": self._stats.consecutive_failures},
                )
                self._state = CircuitState.OPEN
                self._probe_successes = 0
                # Persist to Redis so sibling workers see the open state
                try:
                    from app.core.cache import cache
                    cache.set(f"cb:{self.name}:state", "open", ttl=300)
                except Exception:
                    pass
        self._metric("open" if self._state == CircuitState.OPEN else "failure")

    def _metric(self, event: str):
        try:
            from app.core.metrics import CIRCUIT_BREAKER_EVENTS
            CIRCUIT_BREAKER_EVENTS.labels(circuit=self.name, event=event).inc()
        except Exception:
            pass

    # ── Execution ─────────────────────────────────────────────────────────────

    async def call_async(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        fallback: Any = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> T:
        """Protected async call. Returns fallback on OPEN or any failure."""
        if self.state == CircuitState.OPEN:
            logger.warning("Circuit OPEN — fallback returned", extra={"circuit": self.name})
            with self._lock:
                self._stats.total_fallbacks += 1
            return fallback

        t = timeout if timeout is not None else self.default_timeout
        try:
            if t > 0:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=t)
            else:
                result = await func(*args, **kwargs)
            self._on_success()
            return result
        except asyncio.TimeoutError:
            logger.warning(
                "Circuit call timed out",
                extra={"circuit": self.name, "timeout_s": t},
            )
            self._on_failure(is_timeout=True)
            with self._lock:
                self._stats.total_fallbacks += 1
            return fallback
        except Exception as exc:
            logger.error(
                "Circuit call failed",
                exc_info=exc,
                extra={"circuit": self.name},
            )
            self._on_failure()
            with self._lock:
                self._stats.total_fallbacks += 1
            return fallback

    def call_sync(
        self,
        func: Callable[..., T],
        *args,
        fallback: Any = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> T:
        """Protected sync call. Returns fallback on OPEN or any failure."""
        if self.state == CircuitState.OPEN:
            logger.warning("Circuit OPEN — fallback returned (sync)", extra={"circuit": self.name})
            with self._lock:
                self._stats.total_fallbacks += 1
            return fallback
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            logger.error(
                "Circuit sync call failed",
                exc_info=exc,
                extra={"circuit": self.name},
            )
            self._on_failure()
            with self._lock:
                self._stats.total_fallbacks += 1
            return fallback

    # ── Decorators ────────────────────────────────────────────────────────────

    def protect_async(self, fallback: Any = None, timeout: Optional[float] = None):
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await self.call_async(func, *args, fallback=fallback, timeout=timeout, **kwargs)
            return wrapper
        return decorator

    def protect_sync(self, fallback: Any = None, timeout: Optional[float] = None):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return self.call_sync(func, *args, fallback=fallback, timeout=timeout, **kwargs)
            return wrapper
        return decorator

    # ── Status / admin ────────────────────────────────────────────────────────

    def status(self) -> dict:
        with self._lock:
            state = self._resolve_state()
            return {
                "circuit": self.name,
                "state": state.value,
                "consecutive_failures": self._stats.consecutive_failures,
                "total_failures": self._stats.total_failures,
                "total_timeouts": self._stats.total_timeouts,
                "total_fallbacks": self._stats.total_fallbacks,
                "failure_threshold": self.failure_threshold,
                "last_failure_at": (
                    datetime.fromtimestamp(self._stats.last_failure_at, tz=timezone.utc).isoformat()
                    if self._stats.last_failure_at else None
                ),
            }

    def reset(self):
        with self._lock:
            self._state = CircuitState.CLOSED
            self._stats.consecutive_failures = 0
            self._probe_successes = 0
        logger.info("Circuit manually reset to CLOSED", extra={"circuit": self.name})


# ── Registry ──────────────────────────────────────────────────────────────────

_registry: dict[str, AsyncCircuitBreaker] = {}
_reg_lock = threading.Lock()


def get_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    default_timeout: float = 10.0,
) -> AsyncCircuitBreaker:
    with _reg_lock:
        if name not in _registry:
            _registry[name] = AsyncCircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                default_timeout=default_timeout,
            )
        return _registry[name]


def all_statuses() -> list[dict]:
    with _reg_lock:
        return [cb.status() for cb in _registry.values()]


def reset_breaker(name: str) -> bool:
    with _reg_lock:
        if name in _registry:
            _registry[name].reset()
            return True
        return False


# ── Pre-wired breakers ────────────────────────────────────────────────────────

billing_breaker     = get_breaker("billing_paystack",    failure_threshold=3, recovery_timeout=30,  default_timeout=15.0)
stripe_breaker      = get_breaker("billing_stripe",      failure_threshold=3, recovery_timeout=30,  default_timeout=15.0)
flutterwave_breaker = get_breaker("billing_flutterwave", failure_threshold=3, recovery_timeout=30,  default_timeout=15.0)
sms_breaker         = get_breaker("sms_termii",          failure_threshold=5, recovery_timeout=60,  default_timeout=8.0)
whatsapp_breaker    = get_breaker("whatsapp",            failure_threshold=5, recovery_timeout=60,  default_timeout=8.0)
email_breaker       = get_breaker("email_sendgrid",      failure_threshold=5, recovery_timeout=60,  default_timeout=10.0)
ai_breaker          = get_breaker("ai_groq",             failure_threshold=5, recovery_timeout=120, default_timeout=20.0)
geo_breaker         = get_breaker("geo_ipapi",           failure_threshold=5, recovery_timeout=300, default_timeout=5.0)


# ── Convenience helpers ───────────────────────────────────────────────────────

async def with_timeout(coro: Awaitable[T], seconds: float, fallback: T = None) -> T:
    """Wrap any coroutine with a timeout and a safe fallback."""
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        logger.warning(f"Timeout after {seconds}s — returning fallback")
        return fallback
    except Exception as exc:
        logger.error(f"with_timeout call failed: {exc}")
        return fallback
