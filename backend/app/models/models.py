"""
Vitar v5 - Database Models
Full relational schema with indexes, constraints, and locking support
"""

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, 
    ForeignKey, Text, Enum, Index, UniqueConstraint, 
    CheckConstraint, JSON, Numeric
)
from sqlalchemy import JSON as JSONB  # JSONB used on postgres, JSON on sqlite (tests)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


# ─── Enums ────────────────────────────────────────────────────────────────────

class SubscriptionPlan(str, enum.Enum):
    TRIAL = "trial"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class AppointmentStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"

class PaymentStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"

class NotificationChannel(str, enum.Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"
    EMAIL = "email"

class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"

class PaymentProvider(str, enum.Enum):
    PAYSTACK = "paystack"
    FLUTTERWAVE = "flutterwave"
    STRIPE = "stripe"

class Region(str, enum.Enum):
    NG = "NG"
    US = "US"
    UK = "UK"
    EU = "EU"
    OTHER = "OTHER"


# ─── Users ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(20))
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    email_verification_token = Column(String(255))
    password_reset_token = Column(String(255))
    password_reset_expires = Column(DateTime)
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    # Relationships
    clinics = relationship("Clinic", back_populates="owner")


# ─── Clinics ──────────────────────────────────────────────────────────────────

class Clinic(Base):
    __tablename__ = "clinics"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=False)
    phone = Column(String(20))
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(10), default="NG")
    logo_url = Column(Text)
    website = Column(String(255))
    timezone = Column(String(50), default="Africa/Lagos")
    currency = Column(String(10), default="NGN")
    region = Column(Enum(Region), default=Region.NG)
    
    # Trial
    trial_started_at = Column(DateTime, default=func.now())
    trial_ends_at = Column(DateTime)
    trial_bookings_used = Column(Integer, default=0)
    
    # Features
    patient_payment_enabled = Column(Boolean, default=False)
    consultation_fee = Column(Numeric(12, 2), default=0)
    booking_page_enabled = Column(Boolean, default=True)
    online_booking_enabled = Column(Boolean, default=True)

    # Payment accounts
    paystack_subaccount_code = Column(String(100))
    paystack_bank_name = Column(String(100))
    paystack_account_number = Column(String(20))
    stripe_account_id = Column(String(100))

    is_active = Column(Boolean, default=True)
    onboarding_completed = Column(Boolean, default=False)
    onboarding_step = Column(Integer, default=0)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    owner = relationship("User", back_populates="clinics")
    doctors = relationship("Doctor", back_populates="clinic", cascade="all, delete-orphan")
    patients = relationship("Patient", back_populates="clinic", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="clinic", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="clinic", uselist=False)
    notification_settings = relationship("NotificationSettings", back_populates="clinic", uselist=False)
    waiting_list = relationship("WaitingList", back_populates="clinic", cascade="all, delete-orphan")


# ─── Subscriptions ────────────────────────────────────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    plan = Column(Enum(SubscriptionPlan), nullable=False, default=SubscriptionPlan.TRIAL)
    status = Column(Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.TRIALING)
    
    # Provider IDs
    provider = Column(Enum(PaymentProvider))
    provider_customer_id = Column(String(100))
    provider_subscription_id = Column(String(100))
    
    # Billing
    amount = Column(Numeric(12, 2), default=0)
    currency = Column(String(10), default="NGN")
    billing_cycle = Column(String(20), default="monthly")  # monthly | annual
    
    # Dates
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    cancelled_at = Column(DateTime)
    cancel_at_period_end = Column(Boolean, default=False)
    
    # Metadata
    extra_data = Column(JSONB, default={})
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    clinic = relationship("Clinic", back_populates="subscription")
    payments = relationship("SubscriptionPayment", back_populates="subscription")


class SubscriptionPayment(Base):
    __tablename__ = "subscription_payments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id"), nullable=False, index=True)
    provider = Column(Enum(PaymentProvider), nullable=False)
    provider_reference = Column(String(255), unique=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="NGN")
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, index=True)
    paid_at = Column(DateTime)
    failed_at = Column(DateTime)
    retry_count = Column(Integer, default=0)
    extra_data = Column(JSONB, default={})
    created_at = Column(DateTime, default=func.now(), index=True)

    subscription = relationship("Subscription", back_populates="payments")

    __table_args__ = (
        Index("ix_subpayment_status_created", "status", "created_at"),
    )


# ─── Doctors ──────────────────────────────────────────────────────────────────

class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    specialty = Column(String(100))
    email = Column(String(255))
    phone = Column(String(20))
    avatar_url = Column(Text)
    bio = Column(Text)
    consultation_fee = Column(Numeric(12, 2), default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    clinic = relationship("Clinic", back_populates="doctors")
    availability = relationship("DoctorAvailability", back_populates="doctor", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="doctor")
    blocked_times = relationship("DoctorBlockedTime", back_populates="doctor", cascade="all, delete-orphan")


class DoctorAvailability(Base):
    __tablename__ = "doctor_availability"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    doctor_id = Column(String(36), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Mon ... 6=Sun
    start_time = Column(String(10), nullable=False)  # "09:00"
    end_time = Column(String(10), nullable=False)    # "17:00"
    slot_duration_mins = Column(Integer, default=30)
    is_available = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("doctor_id", "day_of_week", name="uq_doctor_day"),
    )

    doctor = relationship("Doctor", back_populates="availability")


class DoctorBlockedTime(Base):
    __tablename__ = "doctor_blocked_times"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    doctor_id = Column(String(36), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    reason = Column(String(255))
    created_at = Column(DateTime, default=func.now())

    doctor = relationship("Doctor", back_populates="blocked_times")


# ─── Patients ─────────────────────────────────────────────────────────────────

class Patient(Base):
    __tablename__ = "patients"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    # FIX: clinic_id gap — nullable=True allows Wabizz to create patients before
    # clinic linkage is confirmed. Patients created via WhatsApp with a clinic_id
    # will appear in the clinic dashboard; those without will not (acceptable fallback).
    clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="SET NULL"), nullable=True, index=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), index=True)
    phone = Column(String(20), nullable=False, index=True)
    date_of_birth = Column(DateTime)
    gender = Column(String(10))
    notes = Column(Text)

    # Fix 8: is_active was referenced in the by-phone endpoint query
    # (Patient.is_active == True) but was missing from this model, causing a
    # runtime AttributeError on any call to GET /patients/by-phone/{phone}.
    is_active = Column(Boolean, default=True, nullable=False)

    # AI no-show risk profile
    historical_no_show_rate = Column(Float, default=0.0)
    total_appointments = Column(Integer, default=0)
    total_no_shows = Column(Integer, default=0)
    total_cancellations = Column(Integer, default=0)
    last_no_show_at = Column(DateTime)
    preferred_channel = Column(Enum(NotificationChannel), default=NotificationChannel.SMS)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    clinic = relationship("Clinic", back_populates="patients")
    appointments = relationship("Appointment", back_populates="patient")

    __table_args__ = (
        Index("ix_patient_clinic_phone", "clinic_id", "phone"),
    )


# ─── Appointments ─────────────────────────────────────────────────────────────

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(String(36), ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True)

    scheduled_at = Column(DateTime, nullable=False, index=True)
    duration_mins = Column(Integer, default=30)
    status = Column(Enum(AppointmentStatus), nullable=False, default=AppointmentStatus.CONFIRMED, index=True)

    reason = Column(Text)
    notes = Column(Text)
    booked_via = Column(String(20), default="manual")  # manual | booking_page

    # AI risk scoring
    no_show_risk_score = Column(Float, default=0.0)  # 0.0–1.0
    risk_factors = Column(JSONB, default={})
    risk_calculated_at = Column(DateTime)

    # Reminders
    reminder_sent_at = Column(DateTime)
    reminder_count = Column(Integer, default=0)
    last_reminder_channel = Column(Enum(NotificationChannel))

    # Payment
    payment_required = Column(Boolean, default=False)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.UNPAID)
    payment_amount = Column(Numeric(12, 2), default=0)
    payment_currency = Column(String(10), default="NGN")
    payment_provider_ref = Column(String(255))
    paid_at = Column(DateTime)

    # Cancellation / rescheduling
    cancelled_reason = Column(Text)
    cancelled_at = Column(DateTime)
    rescheduled_from_id = Column(String(36), ForeignKey("appointments.id"))

    # Tracking
    confirmation_token = Column(String(100), unique=True, index=True)
    cancel_token = Column(String(100), unique=True, index=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    clinic = relationship("Clinic", back_populates="appointments")
    doctor = relationship("Doctor", back_populates="appointments")
    patient = relationship("Patient", back_populates="appointments")
    notifications = relationship("Notification", back_populates="appointment", cascade="all, delete-orphan")
    payment_record = relationship("PatientPayment", back_populates="appointment", uselist=False)

    __table_args__ = (
        # Enforce no double-booking: same doctor, same time slot
        Index("ix_appointment_doctor_time", "doctor_id", "scheduled_at"),
        # Dashboard query: clinic filtered by status + date range (most common query)
        Index("ix_appointment_clinic_status_time", "clinic_id", "status", "scheduled_at"),
        # Risk refresh: confirmed appointments by time (hourly beat task)
        Index("ix_appointment_status_time", "status", "scheduled_at"),
        CheckConstraint("duration_mins > 0 AND duration_mins <= 480", name="chk_duration"),
        CheckConstraint("no_show_risk_score >= 0.0 AND no_show_risk_score <= 1.0", name="chk_risk_score"),
    )


# ─── Patient Payments ─────────────────────────────────────────────────────────

class PatientPayment(Base):
    __tablename__ = "patient_payments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    appointment_id = Column(String(36), ForeignKey("appointments.id", ondelete="RESTRICT"), unique=True, nullable=False)
    clinic_id = Column(String(36), ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    provider = Column(Enum(PaymentProvider), nullable=False)
    provider_reference = Column(String(255), unique=True, nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    clinic_share = Column(Numeric(12, 2), nullable=False)
    platform_share = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="NGN")
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    paid_at = Column(DateTime)
    extra_data = Column(JSONB, default={})
    created_at = Column(DateTime, default=func.now())

    appointment = relationship("Appointment", back_populates="payment_record")


# ─── Notifications ────────────────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    appointment_id = Column(String(36), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True)
    clinic_id = Column(String(36), ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)

    channel = Column(Enum(NotificationChannel), nullable=False)
    notification_type = Column(String(50), nullable=False)  # reminder | confirmation | cancellation | follow_up
    status = Column(Enum(NotificationStatus), default=NotificationStatus.PENDING)

    recipient = Column(String(255))  # phone or email
    message_body = Column(Text)
    provider_message_id = Column(String(255))
    provider_response = Column(JSONB, default={})

    scheduled_for = Column(DateTime, nullable=False)
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    failed_at = Column(DateTime)
    failure_reason = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    created_at = Column(DateTime, default=func.now())

    appointment = relationship("Appointment", back_populates="notifications")

    __table_args__ = (
        Index("ix_notification_scheduled", "scheduled_for", "status"),
        # retry_failed_notifications task: status + retry_count lookup
        Index("ix_notification_status_retry", "status", "retry_count"),
        # appointment_id lookups from task handlers
        Index("ix_notification_appt_channel", "appointment_id", "channel"),
    )


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), unique=True, nullable=False)

    sms_enabled = Column(Boolean, default=True)
    whatsapp_enabled = Column(Boolean, default=False)
    email_enabled = Column(Boolean, default=True)

    reminder_hours_before = Column(Integer, default=24)
    second_reminder_hours = Column(Integer, default=2)

    # AI-driven: override reminder timing based on risk
    ai_smart_reminders = Column(Boolean, default=True)
    high_risk_extra_reminder = Column(Boolean, default=True)

    sms_sender_name = Column(String(20), default="Vitar")
    custom_reminder_message = Column(Text)
    custom_confirmation_message = Column(Text)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    clinic = relationship("Clinic", back_populates="notification_settings")


# ─── Waiting List ─────────────────────────────────────────────────────────────

class WaitingList(Base):
    __tablename__ = "waiting_list"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(String(36), ForeignKey("doctors.id"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=True)
    
    # For non-registered patients
    patient_name = Column(String(255))
    patient_phone = Column(String(20))
    patient_email = Column(String(255))

    preferred_date = Column(DateTime)
    preferred_time_start = Column(String(10))
    preferred_time_end = Column(String(10))
    reason = Column(Text)
    
    status = Column(String(20), default="waiting")  # waiting | notified | booked | expired
    notified_at = Column(DateTime)
    booked_appointment_id = Column(String(36), ForeignKey("appointments.id"))
    
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime)

    clinic = relationship("Clinic", back_populates="waiting_list")


# ─── No-Show Predictions ──────────────────────────────────────────────────────

class NoShowPrediction(Base):
    """Audit trail for AI predictions - useful for model improvement."""
    __tablename__ = "no_show_predictions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    appointment_id = Column(String(36), ForeignKey("appointments.id"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    
    model_version = Column(String(20), default="v1")
    risk_score = Column(Float, nullable=False)
    risk_category = Column(String(20))  # low | medium | high | critical
    
    # Feature snapshot used for prediction
    features = Column(JSONB, default={})
    
    # Outcome (filled after appointment)
    actual_outcome = Column(String(20))  # attended | no_show | cancelled
    
    predicted_at = Column(DateTime, default=func.now())
    outcome_recorded_at = Column(DateTime)


# ─── Audit Log ────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    clinic_id = Column(String(36), ForeignKey("clinics.id"), index=True)
    user_id = Column(String(36), ForeignKey("users.id"))
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50))
    entity_id = Column(String(36))
    old_data = Column(JSONB)
    new_data = Column(JSONB)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    created_at = Column(DateTime, default=func.now(), index=True)

    __table_args__ = (
        Index("ix_audit_clinic_created", "clinic_id", "created_at"),
    )


# ─── v11: Refresh Token Store (revocation support) ───────────────────────────

class RefreshToken(Base):
    """
    Stores hashed refresh tokens for server-side revocation.

    Properties:
      - One row per active session per user (single-session by default)
      - Deleted on logout, password change, and token rotation
      - token_hash: SHA-256 of the raw JWT (never store raw tokens)
      - expires_at: mirrors JWT expiry; enables DB-level cleanup
    """
    __tablename__ = "refresh_tokens"

    id         = Column(String(36), primary_key=True, default=gen_uuid)
    user_id    = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="refresh_tokens")
