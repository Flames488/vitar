"""AI Core foundation: leads, content_queue, agent_runs, customer_health_signals,
agent_notifications, ai_usage_log

Schema-only foundation for the internal AI Core growth system (Lead Hunter,
Sales Agent, Content Agent, Customer Success — see app/agents/). No agent
logic lives here; this just creates the tables app/models/models.py already
declares matching classes for.

Note: the shared cross-agent notification feed is named agent_notifications,
NOT notifications — that table name is already taken by the existing
Notification model (patient-facing SMS/WhatsApp/email delivery tracking, a
completely different concept from this internal ops alert feed).

Revision ID: 027_ai_core_foundation
Revises: 026_appointment_checks
"""
from alembic import op
import sqlalchemy as sa

revision = "027_ai_core_foundation"
down_revision = "026_appointment_checks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "leads",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("clinic_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("whatsapp", sa.String(20), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_contacted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index(
        "uq_leads_phone", "leads", ["phone"], unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )
    op.create_index("ix_leads_status_score", "leads", ["status", "score"])

    op.create_table(
        "content_queue",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("target_platform", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_by_agent", sa.String(50), nullable=True),
        sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_content_queue_status", "content_queue", ["status"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("task_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("items_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_agent_runs_name_started", "agent_runs", ["agent_name", "started_at"])

    op.create_table(
        "customer_health_signals",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("clinic_id", sa.String(36),
                  sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_type", sa.String(30), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_health_signals_clinic_id", "customer_health_signals", ["clinic_id"])
    op.create_index("ix_health_signals_clinic_status", "customer_health_signals", ["clinic_id", "status"])

    op.create_table(
        "agent_notifications",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("related_id", sa.String(36), nullable=True),
        sa.Column("link_path", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_notifications_is_read", "agent_notifications", ["is_read"])
    op.create_index("ix_agent_notifications_created_at", "agent_notifications", ["created_at"])

    op.create_table(
        "ai_usage_log",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model", sa.String(100), nullable=True),
    )


def downgrade():
    op.drop_table("ai_usage_log")

    op.drop_index("ix_agent_notifications_created_at", table_name="agent_notifications")
    op.drop_index("ix_agent_notifications_is_read", table_name="agent_notifications")
    op.drop_table("agent_notifications")

    op.drop_index("ix_health_signals_clinic_status", table_name="customer_health_signals")
    op.drop_index("ix_health_signals_clinic_id", table_name="customer_health_signals")
    op.drop_table("customer_health_signals")

    op.drop_index("ix_agent_runs_name_started", table_name="agent_runs")
    op.drop_table("agent_runs")

    op.drop_index("ix_content_queue_status", table_name="content_queue")
    op.drop_table("content_queue")

    op.drop_index("ix_leads_status_score", table_name="leads")
    op.drop_index("uq_leads_phone", table_name="leads")
    op.drop_table("leads")
