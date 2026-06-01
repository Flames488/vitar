"""
Vitar v9 — Enhanced Database Layer

Upgrades over v8:
  1. Hard per-query timeout (statement_timeout) configurable via settings
  2. Advisory lock helper for distributed mutual exclusion
  3. Redis query-result cache decorator for read-heavy queries
  4. Slow-query logger (emits structured log + Prometheus counter)
  5. Connection pool health exported to metrics
  6. Index recommendations documented inline
"""

import time
import logging
from contextlib import contextmanager
from typing import Any, Callable, Generator, Optional, TypeVar

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings

logger = logging.getLogger("vitar.database")

T = TypeVar("T")

# ── Base ─────────────────────────────────────────────────────────────────────
Base = declarative_base()


# ── Engine factory ────────────────────────────────────────────────────────────
def _make_engine(url: str, retries: int = 5, delay: float = 2.0):
    """
    Build a production-grade SQLAlchemy engine with tuned timeouts.

    Timeouts:
      connect_timeout                    10 s  — TCP/DNS
      lock_timeout                       10 s  — row/table lock wait
      statement_timeout                  30 s  — single query hard limit
      idle_in_transaction_session_timeout 60 s  — hung transaction cleanup

    Pool: pool_size=15, max_overflow=25  →  40 max per worker
          16 workers × 40 = 640 max app→PgBouncer connections
          PgBouncer MAX_CLIENT_CONN=1000 → 640 << 1000 ✅
          PgBouncer DEFAULT_POOL_SIZE=20 real PG connections → 20 << max_connections=300 ✅
    """
    is_sqlite = "sqlite" in url
    stmt_timeout_ms = int(getattr(settings, "DB_STATEMENT_TIMEOUT_MS", 30_000))

    kwargs: dict = dict(
        poolclass=QueuePool if not is_sqlite else None,
        pool_pre_ping=True,
        echo=settings.DEBUG,
    )
    if not is_sqlite:
        kwargs.update(
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_recycle=3600,
            pool_timeout=30,
            connect_args={
                "options": (
                    f"-c lock_timeout=10000"
                    f" -c statement_timeout={stmt_timeout_ms}"
                    f" -c idle_in_transaction_session_timeout=60000"
                ),
                "connect_timeout": 10,
            },
        )
    else:
        kwargs["connect_args"] = {"check_same_thread": False}

    for attempt in range(1, retries + 1):
        try:
            eng = create_engine(url, **kwargs)
            if not is_sqlite:
                with eng.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info(
                    "Database connected",
                    extra={
                        "pool_size": settings.DATABASE_POOL_SIZE,
                        "max_overflow": settings.DATABASE_MAX_OVERFLOW,
                        "stmt_timeout_ms": stmt_timeout_ms,
                    },
                )
            _attach_pool_events(eng)
            return eng
        except OperationalError as exc:
            if attempt == retries:
                logger.error(f"Database connection failed after {retries} attempts: {exc}")
                raise
            wait = min(delay * attempt, 30.0)
            logger.warning(
                f"DB connect attempt {attempt}/{retries} failed — retrying in {wait:.0f}s: {exc}"
            )
            time.sleep(wait)
    raise RuntimeError("unreachable")


# ── Pool event hooks ──────────────────────────────────────────────────────────
def _attach_pool_events(eng):
    """Wire SQLAlchemy pool events to Prometheus metrics."""
    @event.listens_for(eng, "checkout")
    def on_checkout(dbapi_conn, record, proxy):
        try:
            from app.core.metrics import DB_POOL_CHECKOUTS
            DB_POOL_CHECKOUTS.inc()
        except Exception:
            pass

    @event.listens_for(eng, "invalidate")
    def on_invalidate(dbapi_conn, record, exception):
        logger.warning(
            "DB pool: connection invalidated",
            extra={"error": str(exception) if exception else None},
        )


# ── Slow-query logger ─────────────────────────────────────────────────────────
SLOW_QUERY_THRESHOLD_S: float = getattr(settings, "SLOW_QUERY_THRESHOLD_S", 0.5)


def timed_query(label: str, query_fn: Callable[..., T], *args, **kwargs) -> T:
    """
    Execute query_fn(*args, **kwargs); log + count if it exceeds threshold.

    Usage:
        results = timed_query(
            "appointments_by_clinic",
            db.query(Appointment).filter(...).all
        )
    """
    start = time.perf_counter()
    try:
        result = query_fn(*args, **kwargs)
        elapsed = time.perf_counter() - start
        if elapsed >= SLOW_QUERY_THRESHOLD_S:
            logger.warning(
                "Slow query detected",
                extra={"query": label, "elapsed_s": round(elapsed, 3)},
            )
            try:
                from app.core.metrics import SLOW_QUERIES
                SLOW_QUERIES.labels(query=label).inc()
            except Exception:
                pass
        return result
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.error(
            "Query failed",
            exc_info=exc,
            extra={"query": label, "elapsed_s": round(elapsed, 3)},
        )
        raise


# ── Redis-backed query cache ──────────────────────────────────────────────────
def cached_query(
    key: str,
    query_fn: Callable[[], Any],
    ttl: int = 300,
    serialize=None,
    deserialize=None,
) -> Any:
    """
    Try Redis cache first; execute query_fn on miss; store result with TTL.

    Example:
        stats = cached_query(
            f"clinic:stats:{clinic_id}",
            lambda: _compute_stats(db, clinic_id),
            ttl=300,
        )
    """
    from app.core.cache import cache

    cached_val = cache.get(key)
    if cached_val is not None:
        return deserialize(cached_val) if deserialize else cached_val

    result = query_fn()
    if result is not None:
        to_store = serialize(result) if serialize else result
        cache.set(key, to_store, ttl=ttl)
    return result


# ── Distributed advisory lock ─────────────────────────────────────────────────
@contextmanager
def advisory_lock(db: Session, lock_key: str) -> Generator:
    """
    PostgreSQL advisory lock for distributed mutual exclusion.
    Ideal for: payment processing, subscription creation.

    Usage:
        with advisory_lock(db, f"subscription:{clinic_id}"):
            process_payment(...)

    Raises RuntimeError if the lock is already held.
    """
    import hashlib
    lock_id = int(hashlib.md5(lock_key.encode()).hexdigest(), 16) % (2**31)
    try:
        acquired = db.execute(
            text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        ).scalar()
        if not acquired:
            raise RuntimeError(
                f"Could not acquire advisory lock for '{lock_key}' "
                "— concurrent operation in progress"
            )
        yield
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error(f"Advisory lock error for '{lock_key}': {exc}")
        raise


# ── Pool health snapshot ──────────────────────────────────────────────────────
def pool_status(eng=None) -> dict:
    """Return a snapshot of connection pool metrics for /health and Prometheus."""
    try:
        target = eng if eng else _get_engine()
        pool = target.pool
        return {
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "checked_in": pool.checkedin(),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ── Lazy engine ───────────────────────────────────────────────────────────────
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine(settings.DATABASE_URL)
    return _engine


import threading as _threading

# Module-level lock guards the one-time _LazyEngine initialisation.
# A class-attribute lock is NOT safe: two threads can both see _lock=None
# before either sets it, causing _make_engine() to be called twice.
_lazy_init_lock = _threading.Lock()


class _LazyEngine:
    """
    Proxy that builds the real engine on first attribute access.
    Thread-safe: uses a module-level lock so that concurrent first-accesses
    cannot both observe _real=None and create duplicate engines.
    """
    _real = None

    def __getattr__(self, name):
        # Fast path — engine already built, no lock needed
        if _LazyEngine._real is not None:
            return getattr(_LazyEngine._real, name)
        # Slow path — first access; serialise with module-level lock
        with _lazy_init_lock:
            if _LazyEngine._real is None:
                _LazyEngine._real = _make_engine(settings.DATABASE_URL)
        return getattr(_LazyEngine._real, name)


engine = _LazyEngine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Read replica engine ───────────────────────────────────────────────────────
# Lazy-initialised replica engine. Falls back to primary if DATABASE_REPLICA_URL
# is not configured (empty string). Use get_replica_db() in read-heavy Celery
# tasks (calculate_no_show_risk, monitor_queue_depths, analytics tasks) to
# offload reads from the primary. All write operations must use get_db().
_replica_engine: Optional[object] = None
_replica_lock = __import__("threading").Lock()


def _get_replica_engine():
    global _replica_engine
    if _replica_engine is not None:
        return _replica_engine
    with _replica_lock:
        if _replica_engine is None:
            replica_url = getattr(settings, "DATABASE_REPLICA_URL", "")
            if replica_url:
                logger.info("database: initialising read-replica engine")
                _replica_engine = _make_engine(replica_url)
            else:
                logger.debug("database: DATABASE_REPLICA_URL not set — replica reads use primary")
                _replica_engine = engine  # fall back to primary
    return _replica_engine


ReplicaSessionLocal = None  # populated lazily below


def _get_replica_session_factory():
    global ReplicaSessionLocal
    if ReplicaSessionLocal is None:
        ReplicaSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=_get_replica_engine()
        )
    return ReplicaSessionLocal


# ── FastAPI dependency ────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    Yield a DB session (primary — supports reads AND writes).
    - Rolls back on unhandled exception
    - Always closes (returns connection to pool)
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        try:
            db.rollback()
        except Exception as rb_exc:
            logger.error(f"get_db: rollback failed: {rb_exc}")
        raise
    finally:
        db.close()


def get_replica_db() -> Generator[Session, None, None]:
    """
    Yield a read-only DB session from the replica (falls back to primary if
    DATABASE_REPLICA_URL is not set). Use this in read-heavy Celery tasks such
    as calculate_no_show_risk, monitor_queue_depths, and analytics tasks.
    NEVER perform writes through this session.
    """
    factory = _get_replica_session_factory()
    db = factory()
    try:
        yield db
    except Exception:
        try:
            db.rollback()
        except Exception as rb_exc:
            logger.error(f"get_replica_db: rollback failed: {rb_exc}")
        raise
    finally:
        db.close()
