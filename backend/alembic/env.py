"""
Vitar — Alembic Migration Environment

Enhancements over the base template:
  - Connection retry with exponential backoff (5 attempts, up to ~30s)
  - compare_type=True: detects column type changes in autogenerate
  - NullPool: appropriate for one-shot migration runs
  - All models imported via wildcard so autogenerate sees all tables
  - create_engine bypass: avoids configparser % interpolation bug on
    URL-encoded passwords (e.g. Flames48%40%21 triggers ValueError)
"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, create_engine, pool, text
from sqlalchemy.exc import OperationalError
from alembic import context
import os
import sys
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.database import Base
from app.models.models import *  # noqa

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

logger = logging.getLogger("alembic.env")


# ── Retry helper ──────────────────────────────────────────────────────────────

def _connect_with_retry(engine, max_attempts: int = 5, base_delay: float = 1.0):
    """
    Attempt to connect, retrying with exponential backoff.

    Backoff schedule (base_delay=1.0s):
      Attempt 1: immediate
      Attempt 2: 1s delay
      Attempt 3: 2s delay
      Attempt 4: 4s delay
      Attempt 5: 8s delay
      Total worst case: ~15s
    """
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            conn = engine.connect()
            conn.execute(text("SELECT 1"))
            return conn
        except OperationalError as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Database connection attempt %d/%d failed: %s — retrying in %.1fs",
                    attempt, max_attempts, exc.orig, delay
                )
                time.sleep(delay)
            else:
                logger.error(
                    "Database not available after %d attempts. Last error: %s",
                    max_attempts, exc
                )
    raise last_exc


# ── Offline mode ──────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """Generate SQL script without a live DB connection (CI preview)."""
    # For offline mode we still need a URL — escape % for configparser safety
    migration_url = os.environ.get("MIGRATION_DATABASE_URL") or settings.DATABASE_URL
    context.configure(
        url=migration_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ───────────────────────────────────────────────────────────────

def run_migrations_online() -> None:
    """
    Connect to the live database and apply migrations.

    Uses create_engine() directly instead of engine_from_config() to
    bypass configparser's % interpolation. configparser treats % as a
    special character, so URL-encoded passwords (e.g. Flames48%40%21)
    raise ValueError: invalid interpolation syntax.

    Using create_engine() directly means the URL never passes through
    configparser — it goes straight to SQLAlchemy.
    """
    migration_url = os.environ.get("MIGRATION_DATABASE_URL") or settings.DATABASE_URL

    connectable = create_engine(
        migration_url,
        poolclass=pool.NullPool,
    )

    connection = _connect_with_retry(connectable, max_attempts=5, base_delay=1.0)

    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=False,
            include_object=lambda obj, name, type_, reflected, compare_to: (
                type_ != "table" or name in target_metadata.tables
            ) if type_ == "table" and reflected else True,
        )
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.close()
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()