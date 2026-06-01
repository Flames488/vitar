"""
Vitar v8 — System-Wide Auto-Recovery & Self-Healing

Covers:
  A. DB startup readiness with exponential backoff
  B. Circuit breaker for external services (payments, emails, AI)
  C. Worker health watchdog hooks
  D. Graceful degradation registry
"""

import time
import logging
import threading
import functools
from enum import Enum
from typing import Callable, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger("vitar.recovery")


# ─── A. DB Readiness ──────────────────────────────────────────────────────────

def wait_for_db(engine, max_retries: int = 15, base_delay: float = 2.0) -> None:
    """
    Block until the DB is ready or raise RuntimeError after max_retries.
    Uses exponential backoff capped at 30s. Safe to call from entrypoint
    AND from lifespan (idempotent — succeeds immediately when DB is up).
    """
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("DB readiness check passed", extra={"attempt": attempt})
            return
        except OperationalError as exc:
            delay = min(base_delay * (2 ** (attempt - 1)), 30.0)
            if attempt == max_retries:
                logger.error(
                    "DB not ready after max retries — aborting",
                    extra={"attempts": max_retries, "error": str(exc)},
                )
                raise RuntimeError(f"Database not ready after {max_retries} attempts: {exc}") from exc
            logger.warning(
                f"DB not ready (attempt {attempt}/{max_retries}) — retrying in {delay:.0f}s",
                extra={"attempt": attempt, "delay": delay, "error": str(exc)},
            )
            time.sleep(delay)


# ─── B. Circuit Breaker ───────────────────────────────────────────────────────

class CircuitState(Enum):
    CLOSED   = "closed"    # Normal — requests pass through
    OPEN     = "open"      # Tripped — requests fail fast
    HALF_OPEN = "half_open" # Probing — one test request allowed


class CircuitBreaker:
    """
    Thread-safe circuit breaker for external service calls.

    Usage:
        cb = CircuitBreaker("stripe", failure_threshold=5, recovery_timeout=60)

        @cb.call
        def charge_card(amount):
            return stripe.PaymentIntent.create(...)

        # Or inline:
        result = cb.execute(lambda: stripe.charge(...))
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if (time.monotonic() - (self._last_failure_time or 0)) >= self.recovery_timeout:
                    logger.info(
                        f"Circuit {self.name}: OPEN → HALF_OPEN (probing)",
                        extra={"circuit": self.name},
                    )
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        state = self.state
        if state == CircuitState.OPEN:
            raise CircuitOpenError(f"Circuit '{self.name}' is OPEN — failing fast")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as exc:
            self._on_failure()
            raise

    def _on_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    f"Circuit {self.name}: HALF_OPEN → CLOSED (probe succeeded)",
                    extra={"circuit": self.name},
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None

    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.error(
                        f"Circuit {self.name}: → OPEN after {self._failure_count} failures",
                        extra={"circuit": self.name, "failures": self._failure_count},
                    )
                self._state = CircuitState.OPEN

    def call(self, func: Callable) -> Callable:
        """Decorator variant."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return self.execute(func, *args, **kwargs)
        return wrapper

    def status(self) -> dict:
        return {
            "circuit": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "last_failure": (
                datetime.fromtimestamp(self._last_failure_time, tz=timezone.utc).isoformat()
                if self._last_failure_time else None
            ),
        }


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is OPEN and a call is attempted."""


# ─── C. Global Circuit Breakers ───────────────────────────────────────────────
# Pre-wired breakers for all external integrations.
# Import these in service modules instead of calling external APIs directly.

_breakers: dict[str, CircuitBreaker] = {}


def get_circuit(name: str, failure_threshold: int = 5, recovery_timeout: float = 60.0) -> CircuitBreaker:
    """Get or create a named circuit breaker (singleton per name)."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
    return _breakers[name]


# Pre-defined circuits for known integrations
stripe_circuit       = get_circuit("stripe",       failure_threshold=3, recovery_timeout=30)
paystack_circuit     = get_circuit("paystack",     failure_threshold=3, recovery_timeout=30)
flutterwave_circuit  = get_circuit("flutterwave",  failure_threshold=3, recovery_timeout=30)
email_circuit        = get_circuit("email",        failure_threshold=5, recovery_timeout=60)
sms_circuit          = get_circuit("sms",          failure_threshold=5, recovery_timeout=60)
whatsapp_circuit     = get_circuit("whatsapp",     failure_threshold=5, recovery_timeout=60)
ai_circuit           = get_circuit("ai_groq",      failure_threshold=5, recovery_timeout=120)
geo_circuit          = get_circuit("geo_ipapi",    failure_threshold=5, recovery_timeout=300)


def all_circuit_statuses() -> list[dict]:
    return [cb.status() for cb in _breakers.values()]


# ─── D. Retry Decorator ───────────────────────────────────────────────────────

def with_retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    exceptions: tuple = (Exception,),
    circuit: Optional[CircuitBreaker] = None,
):
    """
    Decorator: retry a function with exponential backoff.
    Optionally wire to a CircuitBreaker.

    Usage:
        @with_retry(max_attempts=3, backoff_base=2.0, circuit=stripe_circuit)
        def charge_stripe(amount): ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    if circuit:
                        return circuit.execute(func, *args, **kwargs)
                    return func(*args, **kwargs)
                except CircuitOpenError:
                    raise  # Don't retry if circuit is open
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = backoff_base * (2 ** (attempt - 1))
                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed — retrying in {delay:.1f}s",
                        extra={"function": func.__name__, "attempt": attempt, "error": str(exc)},
                    )
                    time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator
