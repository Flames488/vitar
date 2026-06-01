"""
Vitar v5 - Core Utilities

utcnow() returns current UTC time as a timezone-naive datetime, consistent
with SQLAlchemy DateTime columns (stored/returned without tzinfo).
Use this instead of deprecated datetime.utcnow() everywhere.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return current UTC time as timezone-naive datetime (matches DB storage)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
