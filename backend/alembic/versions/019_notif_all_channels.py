"""Turn on SMS/WhatsApp/Email reminders for every existing clinic

New clinics already get all three channels on by default (see
_create_default_notification_settings in auth.py and the NotificationSettings
model default). This is the retroactive half: clinics created before that
default existed may have whatsapp_enabled=false (the old column default),
or any channel manually turned off. Per explicit request, this turns all
three on for every clinic that already exists.

Revision ID: 019_notif_all_channels
Revises: 018_bank_account_unique
"""
from alembic import op

revision = "019_notif_all_channels"
down_revision = "018_bank_account_unique"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE notification_settings
        SET sms_enabled = true, whatsapp_enabled = true, email_enabled = true;
    """)


def downgrade():
    # No safe downgrade — we don't have a record of which clinics had which
    # channel off before this ran, so there's nothing meaningful to restore.
    pass
