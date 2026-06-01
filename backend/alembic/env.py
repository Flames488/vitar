"""
Vitar — Alembic Migration Environment

Enhancements over the base template:
  - Connection retry with exponential backoff (5 attempts, up to ~30s)
    Prevents cold-start failures when Postgres is still booting alongside the
    API container. Without this, `alembic upgrade head` fails instantly if
    Postgres isn't ready yet — even when entrypoint.sh has already confirmed
    connectivity, because the migration step gets a fresh connection attempt.
  - compare_type=True: detects column type changes in autogenerate
  - NullPool: appropriate for one-shot migration runs (no persistent connections)
  - All models imported via wildcard so autogenerate sees all tables
"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.exc import OperationalError
from alembic import context
import os
import sys
import time
import logging

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.database import Base
from app.models.models import *  # noqa — register all models before autogenerate

config = context.config

# Override the sqlalchemy.url from settings so alembic.ini placeholder is ignored.
# Use MIGRATION_DATABASE_URL when set — this is a DIRECT postgres URL that bypasses
# pgbouncer. pgbouncer transaction-pooling mode is incompatible with Alembic DDL
# transactions because they require a persistent session-mode connection.
# In production docker-compose, MIGRATION_DATABASE_URL=...@postgres:5432/vitar
# while DATABASE_URL=...@pgbouncer:5432/vitar (pooled, for the app).
_migration_url = os.environ.get("MIGRATION_DATABASE_URL") or settings.DATABASE_URL
config.set_main_option("sqlalchemy.url", _migration_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

logger = logging.getLogger("alembic.env")


# ── Retry helper ──────────────────────────────────────────────────────────────

def _connect_with_retry(engine, max_attempts: int = 5, base_delay: float = 1.0):
    """
    Attempt to connect to the database, retrying with exponential backoff.

    This is necessary in Docker Compose environments where:
    - entrypoint.sh has confirmed TCP connectivity to Postgres
    - BUT Postgres is still in recovery/startup mode and not yet accepting queries
    - The window is typically < 5 seconds but can be longer on slow hosts

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
            # Verify connection is actually usable
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
    """
    Offline mode: generate SQL script without a live DB connection.
    Used by CI to preview migrations before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
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
    Online mode: connect to the live database and apply migrations.
    Uses NullPool (no persistent connections) since this runs once per deploy.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Use retry wrapper instead of plain connect()
    connection = _connect_with_retry(connectable, max_attempts=5, base_delay=1.0)

    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # Include schemas needed by the app
            include_schemas=False,
            # Prevent accidental drops of tables not in our models
            # (e.g. Supabase system tables if ever migrated to vanilla Postgres)
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
