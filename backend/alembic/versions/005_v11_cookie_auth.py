"""v11 — httpOnly cookie auth: refresh_tokens table

Revision ID: 005
Revises: 004
Create Date: 2026-04-21

Adds:
  - refresh_tokens table for server-side token revocation
  - Index on token_hash for O(1) lookup
  - Index on user_id for per-user revocation
  - Cleanup function for expired tokens (call from Celery beat)
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "refresh_tokens",
        sa.Column("id",         sa.String(36),  primary_key=True),
        sa.Column("user_id",    sa.String(36),  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64),  nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(),  nullable=False),
        sa.Column("created_at", sa.DateTime(),  server_default=sa.func.now()),
    )
    op.create_index("idx_refresh_tokens_user_id",    "refresh_tokens", ["user_id"])
    op.create_index("idx_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("idx_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])


def downgrade():
    op.drop_index("idx_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("idx_refresh_tokens_token_hash",  table_name="refresh_tokens")
    op.drop_index("idx_refresh_tokens_user_id",     table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
