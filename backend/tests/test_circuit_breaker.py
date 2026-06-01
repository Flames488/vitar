"""
Tests for app/core/circuit_breaker.py
Target: AsyncCircuitBreaker state machine, call_async, fallback handling,
        protect_async decorator, statistics tracking.

Coverage goals: ≥90% of circuit_breaker.py
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.circuit_breaker import (
    AsyncCircuitBreaker,
    CircuitState,
    _Stats,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cb():
    """Fresh circuit breaker with low thresholds for fast tests."""
    return AsyncCircuitBreaker(
        name="test-breaker",
        failure_threshold=3,
        recovery_timeout=0.1,   # 100ms — fast for tests
        success_threshold=2,
        default_timeout=5.0,
    )


# ── Initial state ─────────────────────────────────────────────────────────────

def test_initial_state_closed(cb):
    assert cb.state == CircuitState.CLOSED


def test_initial_stats_zeros(cb):
    assert cb._stats.total_calls == 0
    assert cb._stats.total_failures == 0
    assert cb._stats.consecutive_failures == 0


# ── Successful calls ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_successful_call_returns_value(cb):
    async def good():
        return "result"

    result = await cb.call_async(good)
    assert result == "result"


@pytest.mark.asyncio
async def test_successful_call_increments_total_calls(cb):
    async def good():
        return 42

    await cb.call_async(good)
    assert cb._stats.total_calls == 1


@pytest.mark.asyncio
async def test_successful_call_resets_consecutive_failures(cb):
    # Fail twice then succeed
    async def fail():
        raise RuntimeError("boom")

    async def good():
        return "ok"

    for _ in range(2):
        try:
            await cb.call_async(fail)
        except RuntimeError:
            pass

    assert cb._stats.consecutive_failures == 2

    try:
        await cb.call_async(good)
    except Exception:
        pass

    assert cb._stats.consecutive_failures == 0


# ── Failure handling ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failures_increment_consecutive_counter(cb):
    async def fail():
        raise ValueError("bad")

    for i in range(2):
        try:
            await cb.call_async(fail)
        except ValueError:
            pass

    assert cb._stats.consecutive_failures == 2
    assert cb._stats.total_failures == 2


@pytest.mark.asyncio
async def test_breaker_opens_after_failure_threshold(cb):
    async def fail():
        raise RuntimeError("error")

    for _ in range(cb.failure_threshold):
        try:
            await cb.call_async(fail)
        except RuntimeError:
            pass

    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_open_breaker_returns_fallback_without_calling_fn(cb):
    call_count = 0

    async def fail():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("error")

    # Open the breaker
    for _ in range(cb.failure_threshold):
        try:
            await cb.call_async(fail)
        except RuntimeError:
            pass

    assert cb.state == CircuitState.OPEN
    previous_calls = call_count

    # Now call with fallback — fn should NOT be invoked
    result = await cb.call_async(fail, fallback={"status": "degraded"})
    assert result == {"status": "degraded"}
    assert call_count == previous_calls  # fn was not called again


@pytest.mark.asyncio
async def test_open_breaker_raises_without_fallback(cb):
    async def fail():
        raise RuntimeError("error")

    for _ in range(cb.failure_threshold):
        try:
            await cb.call_async(fail)
        except Exception:
            pass

    with pytest.raises(Exception, match="open"):
        await cb.call_async(fail)


# ── Recovery (HALF_OPEN → CLOSED) ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_breaker_enters_half_open_after_recovery_timeout(cb):
    async def fail():
        raise RuntimeError("error")

    for _ in range(cb.failure_threshold):
        try:
            await cb.call_async(fail)
        except RuntimeError:
            pass

    assert cb.state == CircuitState.OPEN

    # Wait for recovery_timeout (100ms in fixture)
    await asyncio.sleep(cb.recovery_timeout + 0.05)
    assert cb.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_half_open_closes_after_success_threshold(cb):
    async def fail():
        raise RuntimeError("error")

    async def good():
        return "ok"

    # Open the breaker
    for _ in range(cb.failure_threshold):
        try:
            await cb.call_async(fail)
        except RuntimeError:
            pass

    await asyncio.sleep(cb.recovery_timeout + 0.05)
    assert cb.state == CircuitState.HALF_OPEN

    # success_threshold = 2 successes needed to close
    for _ in range(cb.success_threshold):
        result = await cb.call_async(good)
        assert result == "ok"

    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_half_open_failure_reopens_breaker(cb):
    async def fail():
        raise RuntimeError("error")

    for _ in range(cb.failure_threshold):
        try:
            await cb.call_async(fail)
        except RuntimeError:
            pass

    await asyncio.sleep(cb.recovery_timeout + 0.05)
    assert cb.state == CircuitState.HALF_OPEN

    try:
        await cb.call_async(fail)
    except RuntimeError:
        pass

    assert cb.state == CircuitState.OPEN


# ── Timeout handling ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeout_triggers_fallback(cb):
    async def slow():
        await asyncio.sleep(10)  # longer than timeout

    result = await cb.call_async(slow, fallback="timed_out", timeout=0.05)
    assert result == "timed_out"


@pytest.mark.asyncio
async def test_timeout_increments_timeout_counter(cb):
    async def slow():
        await asyncio.sleep(10)

    await cb.call_async(slow, fallback=None, timeout=0.05)
    assert cb._stats.total_timeouts >= 1


# ── protect_async decorator ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_protect_async_decorator_passes_through_on_success():
    cb = AsyncCircuitBreaker(name="deco-test", failure_threshold=3)

    @cb.protect_async(fallback="fallback_value")
    async def do_work():
        return "real_value"

    result = await do_work()
    assert result == "real_value"


@pytest.mark.asyncio
async def test_protect_async_decorator_returns_fallback_when_open():
    cb = AsyncCircuitBreaker(name="deco-open", failure_threshold=2)

    @cb.protect_async(fallback={"error": "degraded"})
    async def always_fails():
        raise RuntimeError("boom")

    for _ in range(cb.failure_threshold):
        result = await always_fails()

    # After threshold reached, next call should return fallback
    assert cb.state == CircuitState.OPEN
    result = await always_fails()
    assert result == {"error": "degraded"}


# ── Statistics ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_stats_returns_current_snapshot(cb):
    async def good():
        return 1

    await cb.call_async(good)
    await cb.call_async(good)

    # Access stats directly
    assert cb._stats.total_calls == 2
    assert cb._stats.total_failures == 0


@pytest.mark.asyncio
async def test_fallback_counter_increments(cb):
    async def fail():
        raise RuntimeError("err")

    # Open the breaker
    for _ in range(cb.failure_threshold):
        try:
            await cb.call_async(fail)
        except Exception:
            pass

    # Call with fallback — should increment fallback counter
    await cb.call_async(fail, fallback="fb")
    assert cb._stats.total_fallbacks >= 1


# ── Multiple breakers ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_breakers_are_independent():
    cb1 = AsyncCircuitBreaker("breaker-1", failure_threshold=2)
    cb2 = AsyncCircuitBreaker("breaker-2", failure_threshold=2)

    async def fail():
        raise RuntimeError("err")

    # Open cb1
    for _ in range(cb1.failure_threshold):
        try:
            await cb1.call_async(fail)
        except RuntimeError:
            pass

    assert cb1.state == CircuitState.OPEN
    assert cb2.state == CircuitState.CLOSED  # cb2 unaffected


# ── Predefined breakers from module ───────────────────────────────────────────

def test_module_level_breakers_exist():
    from app.core.circuit_breaker import billing_breaker, ai_breaker
    assert billing_breaker.name is not None
    assert ai_breaker.name is not None
    assert billing_breaker.state == CircuitState.CLOSED
    assert ai_breaker.state == CircuitState.CLOSED
