"""
Vitar v5.2 - Async Database Layer
Provides async SQLAlchemy sessions for non-blocking request handling.
Use `get_async_db` in FastAPI endpoints for full async/await support.
The sync `get_db` in database.py remains for Celery tasks which are
thread-based and cannot use async sessions.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Convert sync postgres:// URL → async postgresql+asyncpg://
def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    # SQLite for tests
    if "sqlite" in url:
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


_async_engine = None
_AsyncSessionLocal = None


def _get_async_engine():
    global _async_engine, _AsyncSessionLocal
    if _async_engine is None:
        db_url = settings.DATABASE_URL
        is_sqlite = "sqlite" in db_url

        kwargs = dict(
            echo=settings.DEBUG,
            pool_pre_ping=True,
        )
        if is_sqlite:
            # SQLite doesn't support connection pooling in async mode
            kwargs["poolclass"] = NullPool
        else:
            kwargs.update(
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                # FIX: match database.py's sync engine — Supabase's transaction
                # pooler closes idle connections well under 3600s, so a 1hr
                # recycle here let asyncpg connections go stale and raise
                # "server closed the connection unexpectedly" under load.
                pool_recycle=300,
                pool_timeout=30,
                connect_args={
                    # FIX: server_settings is sent as a Postgres startup
                    # parameter during the connection handshake. Production's
                    # DATABASE_URL goes straight through Supabase's
                    # transaction-mode pooler (see database.py's sync engine
                    # comment — the local pgbouncer container isn't in the
                    # live path), which validates startup parameters against
                    # an allowlist and rejects anything it doesn't recognize.
                    # {"jit": "off"} isn't on that list, so every single
                    # async DB connection attempt failed outright with
                    # asyncpg.exceptions.ProtocolViolationError: unsupported
                    # startup parameter: jit — meaning every async endpoint
                    # (all of doctors.py/patients.py/appointments.py's
                    # Wabizz routes, plus any other async-session endpoint)
                    # 500'd on every call. prepared_statement_cache_size is
                    # a client-side asyncpg option, not a startup parameter,
                    # so it's unaffected and stays.
                    "prepared_statement_cache_size": 0,
                },
            )

        _async_engine = create_async_engine(_async_url(db_url), **kwargs)
        _AsyncSessionLocal = async_sessionmaker(
            bind=_async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        logger.info("Async DB engine created")
    return _async_engine, _AsyncSessionLocal


async def get_async_db():
    """
    FastAPI dependency — yields an async DB session.
    Use this in endpoints for non-blocking database access:

        @router.get("/appointments")
        async def list_appointments(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(Appointment))
            return result.scalars().all()
    """
    _, SessionLocal = _get_async_engine()
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
