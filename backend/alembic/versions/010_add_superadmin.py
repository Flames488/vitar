"""Add is_superadmin flag to users

Revision ID: 010_add_superadmin
Revises: 009_clinic_qr_code
Create Date: 2026-06-16

Notes:
  - Adds a boolean is_superadmin column to users (default False).
  - No existing user is promoted — use scripts/create_superadmin.py
    to bootstrap the first admin account.
"""
from alembic import op
import sqlalchemy as sa

revision = '010_add_superadmin'
down_revision = '009_clinic_qr_code'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_superadmin', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('users', 'is_superadmin')
