"""
Vitar v5.2 - Metrics & Observability
Exposes Prometheus metrics at /metrics for Prometheus scraping.
Also instruments SQLAlchemy for slow query detection.

Metrics exposed:
  - vitar_http_requests_total          (counter, by method/path/status)
  - vitar_http_request_duration_seconds (histogram)
  - vitar_http_requests_in_flight      (gauge)
  - vitar_celery_tasks_total           (counter, by task/status)
  - vitar_db_slow_queries_total        (counter)
  - vitar_db_query_duration_seconds    (histogram)
  - vitar_cache_hits_total / misses    (counters)
  - vitar_notifications_sent_total     (counter, by channel)

Usage — mount in main.py:
    from app.core.metrics import metrics_router, instrument_sqlalchemy
    app.include_router(metrics_router)
    instrument_sqlalchemy(engine)
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Prometheus client (optional dep — graceful fallback) ──────────────────────
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, CollectorRegistry,
        generate_latest, CONTENT_TYPE_LATEST, REGISTRY,
    )
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False
    logger.warning("prometheus_client not installed — /metrics endpoint disabled. "
                   "Add prometheus-client to requirements.txt to enable.")

# ── Metric definitions ─────────────────────────────────────────────────────────

if _PROM_AVAILABLE:
    HTTP_REQUESTS_TOTAL = Counter(
        "vitar_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
    )
    HTTP_REQUEST_DURATION = Histogram(
        "vitar_http_request_duration_seconds",
        "HTTP request latency",
        ["method", "path"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )
    HTTP_IN_FLIGHT = Gauge(
        "vitar_http_requests_in_flight",
        "Currently active HTTP requests",
    )
    CELERY_TASKS_TOTAL = Counter(
        "vitar_celery_tasks_total",
        "Celery task completions",
        ["task", "status"],
    )
    DB_SLOW_QUERIES = Counter(
        "vitar_db_slow_queries_total",
        "SQL queries exceeding slow threshold",
        ["query_type"],
    )
    DB_QUERY_DURATION = Histogram(
        "vitar_db_query_duration_seconds",
        "SQL query execution time",
        ["query_type"],
        buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
    )
    CACHE_HITS = Counter("vitar_cache_hits_total", "Redis cache hits")
    CACHE_MISSES = Counter("vitar_cache_misses_total", "Redis cache misses")
    NOTIFICATIONS_SENT = Counter(
        "vitar_notifications_sent_total",
        "Notifications dispatched",
        ["channel", "status"],
    )


# ── Safe metric recorders (no-ops if prometheus not available) ─────────────────

def record_request(method: str, path: str, status: int, duration: float):
    if not _PROM_AVAILABLE:
        return
    # Normalise path to avoid high-cardinality label explosion
    import re
    norm = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "/{id}", path, flags=re.I)
    norm = re.sub(r"/\d+", "/{id}", norm)
    try:
        HTTP_REQUESTS_TOTAL.labels(method=method, path=norm, status=str(status)).inc()
        HTTP_REQUEST_DURATION.labels(method=method, path=norm).observe(duration)
    except Exception:
        pass


def record_celery_task(task_name: str, status: str):
    if not _PROM_AVAILABLE:
        return
    short = task_name.split(".")[-1]  # strip module prefix for readability
    try:
        CELERY_TASKS_TOTAL.labels(task=short, status=status).inc()
    except Exception:
        pass


def record_slow_query(query_type: str, duration: float, sql: str):
    if not _PROM_AVAILABLE:
        return
    try:
        DB_SLOW_QUERIES.labels(query_type=query_type).inc()
        logger.warning(
            "SLOW_QUERY detected",
            extra={
                "query_type": query_type,
                "duration_s": round(duration, 3),
                "sql_preview": sql[:200] if sql else "",
            },
        )
    except Exception:
        pass


def record_db_query(query_type: str, duration: float):
    if not _PROM_AVAILABLE:
        return
    try:
        DB_QUERY_DURATION.labels(query_type=query_type).observe(duration)
    except Exception:
        pass


def record_cache_hit():
    if _PROM_AVAILABLE:
        try:
            CACHE_HITS.inc()
        except Exception:
            pass


def record_cache_miss():
    if _PROM_AVAILABLE:
        try:
            CACHE_MISSES.inc()
        except Exception:
            pass


def record_notification(channel: str, status: str):
    if _PROM_AVAILABLE:
        try:
            NOTIFICATIONS_SENT.labels(channel=channel, status=status).inc()
        except Exception:
            pass


# ── SQLAlchemy slow query instrumentation ─────────────────────────────────────

def _slow_query_threshold() -> float:
    try:
        from app.core.config import settings
        return settings.SLOW_QUERY_THRESHOLD_S
    except Exception:
        return 0.5


def instrument_sqlalchemy(engine):
    """
    Attach SQLAlchemy event listeners to track query durations.
    Call once at startup: instrument_sqlalchemy(engine)
    """
    try:
        from sqlalchemy import event

        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            conn.info.setdefault("query_start_time", []).append(time.perf_counter())

        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            total = time.perf_counter() - conn.info["query_start_time"].pop(-1)
            # Classify query type from first keyword
            first_word = statement.strip().split()[0].upper() if statement.strip() else "UNKNOWN"
            record_db_query(first_word, total)
            if total >= _slow_query_threshold():
                record_slow_query(first_word, total, statement)

        logger.info(f"SQLAlchemy slow-query instrumentation active (threshold={_slow_query_threshold()}s)")
    except Exception as exc:
        logger.warning(f"Could not instrument SQLAlchemy: {exc}")


# ── Starlette middleware that records per-request metrics ──────────────────────

class MetricsMiddleware:
    """
    ASGI middleware — wraps each request to record Prometheus metrics.
    Add to FastAPI BEFORE other middleware so timing is accurate:

        app.add_middleware(MetricsMiddleware)
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from starlette.requests import Request
        request = Request(scope)
        path = request.url.path

        # Don't track the /metrics endpoint itself
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

        if _PROM_AVAILABLE:
            try:
                HTTP_IN_FLIGHT.inc()
            except Exception:
                pass

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            record_request(request.method, path, status_code, duration)
            if _PROM_AVAILABLE:
                try:
                    HTTP_IN_FLIGHT.dec()
                except Exception:
                    pass


# ── /metrics endpoint ──────────────────────────────────────────────────────────


# ── v9: New metrics for circuit breakers, queue depths, pool, autoscaling ─────

if _PROM_AVAILABLE:
    CIRCUIT_BREAKER_EVENTS = Counter(
        "vitar_circuit_breaker_events_total",
        "Circuit breaker state transitions and outcomes",
        ["circuit", "event"],
    )
    QUEUE_DEPTH_GAUGE = Gauge(
        "vitar_celery_queue_depth",
        "Current number of tasks in each Celery queue",
        ["queue"],
    )
    DB_POOL_CHECKOUTS = Counter(
        "vitar_db_pool_checkouts_total",
        "Total DB connections checked out from pool",
    )
    DB_POOL_CHECKINS = Counter(
        "vitar_db_pool_checkins_total",
        "Total DB connections returned to pool",
    )
    SLOW_QUERIES = Counter(
        "vitar_db_slow_queries_named_total",
        "Named slow queries exceeding threshold",
        ["query"],
    )
    AUTOSCALE_EVENTS = Counter(
        "vitar_autoscale_events_total",
        "Autoscale decisions fired",
        ["direction", "component"],
    )
    WORKER_COUNT_GAUGE = Gauge(
        "vitar_worker_count",
        "Current number of running worker containers",
    )
    API_REPLICA_GAUGE = Gauge(
        "vitar_api_replica_count",
        "Current number of running API containers",
    )
    # ── v10: System resource metrics ─────────────────────────────────────────
    SYSTEM_CPU_GAUGE = Gauge(
        "vitar_system_cpu_percent",
        "Host CPU usage percent (1s sample)",
    )
    SYSTEM_MEMORY_GAUGE = Gauge(
        "vitar_system_memory_percent",
        "Host memory usage percent",
    )
    SYSTEM_DISK_GAUGE = Gauge(
        "vitar_system_disk_percent",
        "Host disk usage percent",
    )
    SYSTEM_LOAD_GAUGE = Gauge(
        "vitar_system_load_average",
        "Host load average",
        ["interval"],          # labels: 1m, 5m
    )
    SYSTEM_FD_GAUGE = Gauge(
        "vitar_system_open_fds",
        "Open file descriptors for the current process",
    )
    # ── v10: Operational counters ─────────────────────────────────────────────
    STUCK_TASKS_TOTAL = Counter(
        "vitar_celery_stuck_tasks_total",
        "Tasks detected as stuck (running > threshold)",
    )
    CIRCUIT_OPEN_GAUGE = Gauge(
        "vitar_circuit_breaker_open_count",
        "Number of circuit breakers currently in OPEN state",
    )
else:
    # Stubs so imports never fail when prometheus_client is absent
    class _Stub:
        def labels(self, **_): return self
        def inc(self, *_): pass
        def dec(self, *_): pass
        def set(self, *_): pass
        def observe(self, *_): pass

    CIRCUIT_BREAKER_EVENTS = _Stub()
    QUEUE_DEPTH_GAUGE      = _Stub()
    DB_POOL_CHECKOUTS      = _Stub()
    DB_POOL_CHECKINS       = _Stub()
    SLOW_QUERIES           = _Stub()
    AUTOSCALE_EVENTS       = _Stub()
    WORKER_COUNT_GAUGE     = _Stub()
    API_REPLICA_GAUGE      = _Stub()
    SYSTEM_CPU_GAUGE       = _Stub()
    SYSTEM_MEMORY_GAUGE    = _Stub()
    SYSTEM_DISK_GAUGE      = _Stub()
    SYSTEM_LOAD_GAUGE      = _Stub()
    SYSTEM_FD_GAUGE        = _Stub()
    STUCK_TASKS_TOTAL      = _Stub()
    CIRCUIT_OPEN_GAUGE     = _Stub()

from fastapi import APIRouter
from fastapi.responses import Response

metrics_router = APIRouter()


@metrics_router.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Prometheus scrape endpoint. Protected by network policy, not auth."""
    if not _PROM_AVAILABLE:
        return Response(
            content="# prometheus_client not installed\n",
            media_type="text/plain",
            status_code=503,
        )
    try:
        data = generate_latest(REGISTRY)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)
    except Exception as exc:
        logger.error(f"Failed to generate metrics: {exc}")
        return Response(content="# metrics error\n", media_type="text/plain", status_code=500)
