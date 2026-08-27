"""Lead.area — sub-city neighbourhood for closest-first outreach

Lead Hunter now searches OUTREACH_PRIORITY_AREAS one area at a time and
records which area each lead came from. The Sales Agent orders its
outreach drafts by that area's position in the priority list, so clinics
closest to home get contacted first. Nullable — leads from a bare-city
search or scraped before this column keep it unset.

Revision ID: 033_lead_area
Revises: 032_delist_billing_decouple
"""
from alembic import op
import sqlalchemy as sa

revision = "033_lead_area"
down_revision = "032_delist_billing_decouple"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("leads", sa.Column("area", sa.String(length=100), nullable=True))
    op.create_index("ix_leads_city_area", "leads", ["city", "area"])


def downgrade():
    op.drop_index("ix_leads_city_area", table_name="leads")
    op.drop_column("leads", "area")
