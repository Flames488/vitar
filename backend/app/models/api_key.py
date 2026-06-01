"""
Vitar — API Key model for Wabizz machine-to-machine authentication.

The raw key is NEVER stored — only a bcrypt hash.
The plain key is generated once, shown to the admin once, then discarded.
"""

import secrets
import bcrypt
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    # bcrypt hash of the raw key — never store plain text
    key_hash = Column(Text, nullable=False, unique=True)
    # Human-readable label, e.g. "Wabizz Integration"
    label = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # ── Class-level helpers ───────────────────────────────────────────────────

    @classmethod
    def generate(cls, label: str) -> tuple["ApiKey", str]:
        """
        Generate a new ApiKey instance and return (instance, raw_key).

        The raw_key is only available at this moment — the caller must display
        it to the admin once and then discard it.  The instance stores only the
        bcrypt hash.

        Usage:
            api_key_obj, raw_key = ApiKey.generate("Wabizz Integration")
            db.add(api_key_obj)
            db.commit()
            # Show raw_key to admin exactly once
        """
        raw_key = "vitar_" + secrets.token_urlsafe(40)
        hashed = bcrypt.hashpw(raw_key.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

        instance = cls(label=label, key_hash=hashed)
        return instance, raw_key

    def verify(self, raw_key: str) -> bool:
        """Check a plain-text key against the stored hash."""
        try:
            return bcrypt.checkpw(raw_key.encode("utf-8"), self.key_hash.encode("utf-8"))
        except Exception:
            return False

    def touch(self) -> None:
        """Update last_used_at to now. Caller must commit."""
        self.last_used_at = _utcnow()

    def revoke(self) -> None:
        """Set is_active = False. Caller must commit."""
        self.is_active = False
