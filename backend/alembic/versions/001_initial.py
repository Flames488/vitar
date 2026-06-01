"""Initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2025-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20)),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('is_verified', sa.Boolean(), server_default='false'),
        sa.Column('email_verification_token', sa.String(255)),
        sa.Column('password_reset_token', sa.String(255)),
        sa.Column('password_reset_expires', sa.DateTime()),
        sa.Column('last_login_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table('clinics',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20)),
        sa.Column('address', sa.Text()),
        sa.Column('city', sa.String(100)),
        sa.Column('state', sa.String(100)),
        sa.Column('country', sa.String(10), server_default='NG'),
        sa.Column('logo_url', sa.Text()),
        sa.Column('website', sa.String(255)),
        sa.Column('timezone', sa.String(50), server_default='Africa/Lagos'),
        sa.Column('currency', sa.String(10), server_default='NGN'),
        sa.Column('region', sa.String(20), server_default='NG'),
        sa.Column('trial_started_at', sa.DateTime()),
        sa.Column('trial_ends_at', sa.DateTime()),
        sa.Column('trial_bookings_used', sa.Integer(), server_default='0'),
        sa.Column('patient_payment_enabled', sa.Boolean(), server_default='false'),
        sa.Column('consultation_fee', sa.Numeric(12, 2), server_default='0'),
        sa.Column('booking_page_enabled', sa.Boolean(), server_default='true'),
        sa.Column('online_booking_enabled', sa.Boolean(), server_default='true'),
        sa.Column('paystack_subaccount_code', sa.String(100)),
        sa.Column('paystack_bank_name', sa.String(100)),
        sa.Column('paystack_account_number', sa.String(20)),
        sa.Column('stripe_account_id', sa.String(100)),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('onboarding_completed', sa.Boolean(), server_default='false'),
        sa.Column('onboarding_step', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_clinics_slug', 'clinics', ['slug'], unique=True)

    op.create_table('subscriptions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('clinic_id', sa.String(36), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan', sa.String(20), nullable=False, server_default='trial'),
        sa.Column('status', sa.String(20), nullable=False, server_default='trialing'),
        sa.Column('provider', sa.String(20)),
        sa.Column('provider_customer_id', sa.String(100)),
        sa.Column('provider_subscription_id', sa.String(100)),
        sa.Column('amount', sa.Numeric(12, 2), server_default='0'),
        sa.Column('currency', sa.String(10), server_default='NGN'),
        sa.Column('billing_cycle', sa.String(20), server_default='monthly'),
        sa.Column('current_period_start', sa.DateTime()),
        sa.Column('current_period_end', sa.DateTime()),
        sa.Column('cancelled_at', sa.DateTime()),
        sa.Column('cancel_at_period_end', sa.Boolean(), server_default='false'),
        sa.Column('extra_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_subscriptions_clinic', 'subscriptions', ['clinic_id'], unique=True)

    op.create_table('subscription_payments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('subscription_id', sa.String(36), sa.ForeignKey('subscriptions.id'), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('provider_reference', sa.String(255)),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(10), server_default='NGN'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('paid_at', sa.DateTime()),
        sa.Column('extra_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table('doctors',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('clinic_id', sa.String(36), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('specialty', sa.String(100)),
        sa.Column('email', sa.String(255)),
        sa.Column('phone', sa.String(20)),
        sa.Column('avatar_url', sa.Text()),
        sa.Column('bio', sa.Text()),
        sa.Column('consultation_fee', sa.Numeric(12, 2), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_doctors_clinic_id', 'doctors', ['clinic_id'])

    op.create_table('doctor_availability',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('doctor_id', sa.String(36), sa.ForeignKey('doctors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('day_of_week', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.String(10), nullable=False),
        sa.Column('end_time', sa.String(10), nullable=False),
        sa.Column('slot_duration_mins', sa.Integer(), server_default='30'),
        sa.Column('is_available', sa.Boolean(), server_default='true'),
        sa.UniqueConstraint('doctor_id', 'day_of_week', name='uq_doctor_day'),
    )

    op.create_table('doctor_blocked_times',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('doctor_id', sa.String(36), sa.ForeignKey('doctors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('start_at', sa.DateTime(), nullable=False),
        sa.Column('end_at', sa.DateTime(), nullable=False),
        sa.Column('reason', sa.String(255)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table('patients',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('clinic_id', sa.String(36), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255)),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('date_of_birth', sa.DateTime()),
        sa.Column('gender', sa.String(10)),
        sa.Column('notes', sa.Text()),
        sa.Column('historical_no_show_rate', sa.Float(), server_default='0.0'),
        sa.Column('total_appointments', sa.Integer(), server_default='0'),
        sa.Column('total_no_shows', sa.Integer(), server_default='0'),
        sa.Column('total_cancellations', sa.Integer(), server_default='0'),
        sa.Column('last_no_show_at', sa.DateTime()),
        sa.Column('preferred_channel', sa.String(20), server_default='sms'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_patients_clinic_id', 'patients', ['clinic_id'])
    op.create_index('ix_patients_email', 'patients', ['email'])
    op.create_index('ix_patient_clinic_phone', 'patients', ['clinic_id', 'phone'])

    op.create_table('appointments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('clinic_id', sa.String(36), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('doctor_id', sa.String(36), sa.ForeignKey('doctors.id'), nullable=False),
        sa.Column('patient_id', sa.String(36), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(), nullable=False),
        sa.Column('duration_mins', sa.Integer(), server_default='30'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('reason', sa.Text()),
        sa.Column('notes', sa.Text()),
        sa.Column('booked_via', sa.String(20), server_default='manual'),
        sa.Column('no_show_risk_score', sa.Float(), server_default='0.0'),
        sa.Column('risk_factors', postgresql.JSONB(), server_default='{}'),
        sa.Column('risk_calculated_at', sa.DateTime()),
        sa.Column('reminder_sent_at', sa.DateTime()),
        sa.Column('reminder_count', sa.Integer(), server_default='0'),
        sa.Column('last_reminder_channel', sa.String(20)),
        sa.Column('payment_required', sa.Boolean(), server_default='false'),
        sa.Column('payment_status', sa.String(20), server_default='unpaid'),
        sa.Column('payment_amount', sa.Numeric(12, 2), server_default='0'),
        sa.Column('payment_currency', sa.String(10), server_default='NGN'),
        sa.Column('payment_provider_ref', sa.String(255)),
        sa.Column('paid_at', sa.DateTime()),
        sa.Column('cancelled_reason', sa.Text()),
        sa.Column('cancelled_at', sa.DateTime()),
        sa.Column('rescheduled_from_id', sa.String(36), sa.ForeignKey('appointments.id')),
        sa.Column('confirmation_token', sa.String(100)),
        sa.Column('cancel_token', sa.String(100)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_appointments_clinic_id', 'appointments', ['clinic_id'])
    op.create_index('ix_appointments_doctor_id', 'appointments', ['doctor_id'])
    op.create_index('ix_appointments_patient_id', 'appointments', ['patient_id'])
    op.create_index('ix_appointments_scheduled_at', 'appointments', ['scheduled_at'])
    op.create_index('ix_appointments_status', 'appointments', ['status'])
    op.create_index('ix_appointment_doctor_time', 'appointments', ['doctor_id', 'scheduled_at'])
    op.create_index('ix_apt_confirm_token', 'appointments', ['confirmation_token'], unique=True)
    op.create_index('ix_apt_cancel_token', 'appointments', ['cancel_token'], unique=True)

    op.create_table('patient_payments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('appointment_id', sa.String(36), sa.ForeignKey('appointments.id'), nullable=False),
        sa.Column('clinic_id', sa.String(36), sa.ForeignKey('clinics.id'), nullable=False),
        sa.Column('patient_id', sa.String(36), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('provider_reference', sa.String(255), nullable=False),
        sa.Column('total_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('clinic_share', sa.Numeric(12, 2), nullable=False),
        sa.Column('platform_share', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(10), server_default='NGN'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('paid_at', sa.DateTime()),
        sa.Column('extra_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_patient_payments_apt', 'patient_payments', ['appointment_id'], unique=True)
    op.create_index('ix_patient_payments_ref', 'patient_payments', ['provider_reference'], unique=True)

    op.create_table('notifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('appointment_id', sa.String(36), sa.ForeignKey('appointments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('clinic_id', sa.String(36), sa.ForeignKey('clinics.id'), nullable=False),
        sa.Column('patient_id', sa.String(36), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('recipient', sa.String(255)),
        sa.Column('message_body', sa.Text()),
        sa.Column('provider_message_id', sa.String(255)),
        sa.Column('provider_response', postgresql.JSONB(), server_default='{}'),
        sa.Column('scheduled_for', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime()),
        sa.Column('delivered_at', sa.DateTime()),
        sa.Column('failed_at', sa.DateTime()),
        sa.Column('failure_reason', sa.Text()),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column('max_retries', sa.Integer(), server_default='3'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_notifications_appointment_id', 'notifications', ['appointment_id'])
    op.create_index('ix_notification_scheduled', 'notifications', ['scheduled_for', 'status'])

    op.create_table('notification_settings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('clinic_id', sa.String(36), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sms_enabled', sa.Boolean(), server_default='true'),
        sa.Column('whatsapp_enabled', sa.Boolean(), server_default='false'),
        sa.Column('email_enabled', sa.Boolean(), server_default='true'),
        sa.Column('reminder_hours_before', sa.Integer(), server_default='24'),
        sa.Column('second_reminder_hours', sa.Integer(), server_default='2'),
        sa.Column('ai_smart_reminders', sa.Boolean(), server_default='true'),
        sa.Column('high_risk_extra_reminder', sa.Boolean(), server_default='true'),
        sa.Column('sms_sender_name', sa.String(20), server_default='Vitar'),
        sa.Column('custom_reminder_message', sa.Text()),
        sa.Column('custom_confirmation_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_notif_settings_clinic', 'notification_settings', ['clinic_id'], unique=True)

    op.create_table('waiting_list',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('clinic_id', sa.String(36), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('doctor_id', sa.String(36), sa.ForeignKey('doctors.id'), nullable=False),
        sa.Column('patient_id', sa.String(36), sa.ForeignKey('patients.id')),
        sa.Column('patient_name', sa.String(255)),
        sa.Column('patient_phone', sa.String(20)),
        sa.Column('patient_email', sa.String(255)),
        sa.Column('preferred_date', sa.DateTime()),
        sa.Column('preferred_time_start', sa.String(10)),
        sa.Column('preferred_time_end', sa.String(10)),
        sa.Column('reason', sa.Text()),
        sa.Column('status', sa.String(20), server_default='waiting'),
        sa.Column('notified_at', sa.DateTime()),
        sa.Column('booked_appointment_id', sa.String(36), sa.ForeignKey('appointments.id')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime()),
    )
    op.create_index('ix_waiting_list_clinic_id', 'waiting_list', ['clinic_id'])

    op.create_table('no_show_predictions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('appointment_id', sa.String(36), sa.ForeignKey('appointments.id'), nullable=False),
        sa.Column('patient_id', sa.String(36), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('model_version', sa.String(20), server_default='v1'),
        sa.Column('risk_score', sa.Float(), nullable=False),
        sa.Column('risk_category', sa.String(20)),
        sa.Column('features', postgresql.JSONB(), server_default='{}'),
        sa.Column('actual_outcome', sa.String(20)),
        sa.Column('predicted_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('outcome_recorded_at', sa.DateTime()),
    )
    op.create_index('ix_no_show_predictions_apt', 'no_show_predictions', ['appointment_id'])

    op.create_table('audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('clinic_id', sa.String(36), sa.ForeignKey('clinics.id')),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id')),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity_type', sa.String(50)),
        sa.Column('entity_id', sa.String(36)),
        sa.Column('old_data', postgresql.JSONB()),
        sa.Column('new_data', postgresql.JSONB()),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('user_agent', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_audit_clinic_created', 'audit_logs', ['clinic_id', 'created_at'])


def downgrade() -> None:
    for t in ['audit_logs','no_show_predictions','waiting_list','notification_settings',
              'notifications','patient_payments','appointments','patients',
              'doctor_blocked_times','doctor_availability','doctors',
              'subscription_payments','subscriptions','clinics','users']:
        op.drop_table(t)
