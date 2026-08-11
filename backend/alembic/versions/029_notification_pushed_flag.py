"""AI Core Phase 7: agent_notifications.pushed_to_telegram

Separate from is_read on purpose (per the build spec's own reasoning):
is_read is the dashboard's "an admin has seen this" state, while
pushed_to_telegram is "the bot has already sent this to Telegram, don't
send it again". Reusing is_read for both would mean the bot pushing a
notification silently marks it read on the dashboard too — hiding a
genuinely-unseen item from an admin who hasn't opened Telegram yet.

Revision ID: 029_notification_pushed_flag
Revises: 028_sales_agent_columns
"""
from alembic import op
import sqlalchemy as sa

revision = "029_notification_pushed_flag"
down_revision = "028_sales_agent_columns"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_notifications",
        sa.Column("pushed_to_telegram", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_agent_notifications_pushed", "agent_notifications", ["pushed_to_telegram"])


def downgrade():
    op.drop_index("ix_agent_notifications_pushed", table_name="agent_notifications")
    op.drop_column("agent_notifications", "pushed_to_telegram")
