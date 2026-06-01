"""Add api_keys table for Wabizz machine-to-machine authentication

Revision ID: 006
Revises: 005
Create Date: 2026-05-10

Adds:
  - api_keys table (id, key_hash, label, is_active, created_at, last_used_at)
  - Unique index on key_hash (fast lookup + uniqueness guarantee)
  - Partial index on is_active for filtering active keys only
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("key_hash", sa.Text, nullable=False, unique=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Unique index on key_hash (already implied by unique=True, but explicit for clarity)
    op.create_index(
        "ix_api_keys_key_hash",
        "api_keys",
        ["key_hash"],
        unique=True,
    )

    # Partial index: only index active keys (the only ones ever queried at auth time)
    op.execute(
        """
        CREATE INDEX ix_api_keys_active
        ON api_keys (id)
        WHERE is_active = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_api_keys_active")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
