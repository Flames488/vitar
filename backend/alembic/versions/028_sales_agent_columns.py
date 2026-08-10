"""AI Core Phase 3: Sales Agent columns

- content_queue.lead_id: nullable FK to leads — links an outreach_template
  draft back to the lead it's for. Nullable because not every content_queue
  row is lead-related (Content Agent's social_post rows aren't).
- leads.attempt_count: how many times outreach has actually been SENT
  (not just drafted) to this lead — drives the 7-day cooldown and the
  auto-flip-to-lost-after-2-attempts logic in app/agents/sales_agent.py.

Revision ID: 028_sales_agent_columns
Revises: 027_ai_core_foundation
"""
from alembic import op
import sqlalchemy as sa

revision = "028_sales_agent_columns"
down_revision = "027_ai_core_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "content_queue",
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_content_queue_lead_id", "content_queue", ["lead_id"])

    op.add_column(
        "leads",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("leads", "attempt_count")
    op.drop_index("ix_content_queue_lead_id", table_name="content_queue")
    op.drop_column("content_queue", "lead_id")
