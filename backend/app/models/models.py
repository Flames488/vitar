"""
Vitar v5 - Database Models
Full relational schema with indexes, constraints, and locking support

Every Column(Enum(...)) below is declared with native_enum=False. The live
schema was always created with these as plain VARCHAR (see 001_initial.py
and every migration since — no CREATE TYPE ... AS ENUM anywhere), but
without native_enum=False, SQLAlchemy's asyncpg dialect still assumes a
native Postgres enum type exists and generates explicit `::typename`
casts in async queries. Since that type was never actually created, every
async query touching one of these columns (any AsyncSession endpoint —
all of doctors.py/patients.py/appointments.py's Wabizz routes included)
failed with asyncpg.exceptions.UndefinedObjectError: type "..." does not
exist. The sync (psycopg2) engine never hit this because psycopg2 doesn't
require the cast to be pre-resolved the same way. native_enum=False makes
SQLAlchemy's assumption match the schema that has always actually existed
— no migration needed, since the columns were VARCHAR already.
"""

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, Text, Enum, Index, UniqueConstraint,
    CheckConstraint, JSON, Numeric, text
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
    AWAITING_PAYMENT = "awaiting_payment"
    APPROVED = "approved"
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

class PendingPaymentStatus(str, enum.Enum):
    """Status of an automated Paystack subscription payment, before it
    becomes a finalized SubscriptionPayment record."""
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    AMOUNT_MISMATCH = "amount_mismatch"

class PayoutStatus(str, enum.Enum):
    PENDING_PAYOUT = "pending_payout"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Region(str, enum.Enum):
    NG = "NG"
    US = "US"
    UK = "UK"
    EU = "EU"
    OTHER = "OTHER"

class ReferralStatus(str, enum.Enum):
    """Lifecycle: signed_up -> paid (referred clinic's first payment
    confirmed) -> credited (10% discount applied to referrer's next
    invoice), or -> expired (self-referral / abuse detected)."""
    PENDING = "pending"
    SIGNED_UP = "signed_up"
    PAID = "paid"
    CREDITED = "credited"
    EXPIRED = "expired"


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
    is_superadmin = Column(Boolean, default=False, nullable=False)
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
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
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
    region = Column(Enum(Region, native_enum=False), default=Region.NG)
    
    # Trial
    trial_started_at = Column(DateTime, default=func.now())
    trial_ends_at = Column(DateTime)
    trial_bookings_used = Column(Integer, default=0)
    
    # Features
    # Defaults on for every new clinic (patients pay before booking) — still
    # a real per-clinic toggle a clinic can switch off in Settings if they
    # want free booking, not a locked platform policy.
    patient_payment_enabled = Column(Boolean, default=True)
    consultation_fee = Column(Numeric(12, 2), default=0)
    booking_page_enabled = Column(Boolean, default=True)
    online_booking_enabled = Column(Boolean, default=True)

    # Hospital Contact Settings — controls whether patients can contact
    # doctors directly (see doctors.py / booking.py). Both default on
    # ("Enable Both"); a hospital can restrict to one channel or disable
    # direct contact entirely from Hospital Settings.
    contact_whatsapp_enabled = Column(Boolean, default=True, nullable=False, server_default="true")
    contact_call_enabled = Column(Boolean, default=True, nullable=False, server_default="true")

    # Payment accounts
    paystack_subaccount_code = Column(String(100))
    paystack_bank_name = Column(String(100))
    paystack_account_number = Column(String(20))
    stripe_account_id = Column(String(100))

    is_active = Column(Boolean, default=True)
    onboarding_completed = Column(Boolean, default=False)
    onboarding_step = Column(Integer, default=0)
    qr_code_path = Column(Text, nullable=True)

    # Refer & Earn — this clinic's own persistent, shareable code (generated
    # lazily on first request, see referral_service.get_or_create_referral_code).
    referral_code = Column(String(20), unique=True, index=True, nullable=True)

    # Public clinic directory — reuses the existing `slug` above as the
    # public identifier (already used by /book/{slug} and the QR code); no
    # second slug system. is_listed is the single source of truth for public
    # search/page visibility (both endpoints also require is_active — see
    # public_clinics.py) — set true on onboarding completion and on
    # subscription activation (onboarding.py, billing_service.py), set false
    # when an admin disables the clinic (admin_clinics.update_clinic_status).
    # Deliberately independent of trial/subscription status — an active
    # clinic patients already know about (e.g. via QR code) stays
    # searchable even if its trial lapses unpaid; the paywall gates other
    # features, not directory visibility. opening_hours/services have no
    # existing data source or editing UI yet — nullable, omitted from the
    # public page when empty rather than backfilled with placeholder content.
    is_listed = Column(Boolean, default=False, nullable=False, index=True)
    opening_hours = Column(Text, nullable=True)
    services = Column(JSONB, nullable=True)

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
    bank_accounts = relationship("HospitalBankAccount", back_populates="clinic")


# ─── Subscriptions ────────────────────────────────────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    plan = Column(Enum(SubscriptionPlan, native_enum=False), nullable=False, default=SubscriptionPlan.TRIAL)
    status = Column(Enum(SubscriptionStatus, native_enum=False), nullable=False, default=SubscriptionStatus.TRIALING)
    
    # Provider IDs
    provider = Column(Enum(PaymentProvider, native_enum=False))
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
    provider = Column(Enum(PaymentProvider, native_enum=False), nullable=False)
    provider_reference = Column(String(255), unique=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="NGN")
    status = Column(Enum(PaymentStatus, native_enum=False), default=PaymentStatus.PENDING, index=True)
    paid_at = Column(DateTime)
    failed_at = Column(DateTime)
    retry_count = Column(Integer, default=0)
    extra_data = Column(JSONB, default={})
    created_at = Column(DateTime, default=func.now(), index=True)

    subscription = relationship("Subscription", back_populates="payments")

    __table_args__ = (
        Index("ix_subpayment_status_created", "status", "created_at"),
    )


# ─── Automated Paystack Subscription Payments (smart payment system) ─────────

class PendingSubscriptionPayment(Base):
    """
    Tracks an in-flight, automated Paystack subscription payment from the
    moment a clinic clicks "Upgrade" until the webhook confirms (or the
    session expires). On success this is what drives automatic activation
    of the clinic's Subscription — no admin step required.
    """
    __tablename__ = "pending_subscription_payments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)

    subscription_plan = Column(String(20), nullable=False)   # basic | pro | enterprise
    billing_cycle = Column(String(20), default="monthly")    # monthly | annual

    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="NGN")

    paystack_reference = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(Enum(PendingPaymentStatus, native_enum=False), default=PendingPaymentStatus.PENDING, nullable=False, index=True)

    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now(), index=True)
    paid_at = Column(DateTime)

    provider_response = Column(JSONB, default={})

    __table_args__ = (
        Index("ix_pendingpay_status_expires", "status", "expires_at"),
    )


# ─── Referrals (Refer & Earn) ──────────────────────────────────────────────────

class Referral(Base):
    """
    One row per referred clinic signup. `referral_code` is denormalized
    from the referrer's Clinic.referral_code at signup time for audit
    purposes — the source of truth for "whose code is this" is
    Clinic.referral_code (unique, indexed, used for the fast signup-time
    lookup). See app.services.referral_service for the full lifecycle.
    """
    __tablename__ = "referrals"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    referrer_clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    # unique: a clinic can only ever be attributed to one referrer
    referred_clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    referral_code = Column(String(20), nullable=False)
    status = Column(Enum(ReferralStatus, native_enum=False), default=ReferralStatus.SIGNED_UP, nullable=False)

    created_at = Column(DateTime, default=func.now())
    paid_at = Column(DateTime, nullable=True)
    credited_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_referrals_referrer_status", "referrer_clinic_id", "status"),
    )


# ─── Patient Registrations (eRegistration) ─────────────────────────────────────

class RegistrationStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"


class PatientRegistration(Base):
    """
    One row per (patient_id, clinic_id) — a draft is upserted in place and
    becomes 'submitted' rather than a second row being created (see
    __table_args__ unique constraint). registration_token is how an
    unauthenticated patient proves this is their own registration — Vitar
    has no patient login, so this follows the same shape as
    Appointment.confirmation_token/cancel_token rather than assuming a
    session that doesn't exist. See app.api.v1.endpoints.registrations.
    """
    __tablename__ = "patient_registrations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(Enum(RegistrationStatus, native_enum=False), default=RegistrationStatus.DRAFT, nullable=False)

    registration_token = Column(String(100), unique=True, index=True, nullable=False)

    # Personal info
    full_name = Column(String(255))
    phone_number = Column(String(20))
    date_of_birth = Column(DateTime)
    gender = Column(String(10))

    # Address
    state = Column(String(100))
    city = Column(String(100))
    residential_address = Column(Text)

    # Emergency contact
    emergency_contact_name = Column(String(255))
    emergency_contact_relationship = Column(String(100))
    emergency_contact_phone = Column(String(20))

    # Optional health info — plain columns, no encryption-at-rest precedent
    # elsewhere in this schema (see Phase 1 discussion).
    blood_group = Column(String(20))
    genotype = Column(String(20))
    allergies = Column(Text)
    existing_conditions = Column(Text)
    current_medications = Column(Text)

    # Consent — consent_given_at is always set server-side at submission,
    # never trusted from the client.
    consent_given = Column(Boolean, default=False, nullable=False)
    consent_given_at = Column(DateTime(timezone=True), nullable=True)

    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("patient_id", "clinic_id", name="uq_patient_registrations_patient_clinic"),
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

    # Doctor Details — core feature, not gated by subscription/plan. When
    # True, this doctor's contact info is exposed on the public booking
    # page, subject to the hospital's Clinic.contact_whatsapp_enabled /
    # Clinic.contact_call_enabled settings (see booking.py). Hospital admins
    # can still turn this off for an individual doctor who shouldn't be
    # contacted directly.
    doctor_details_enabled = Column(Boolean, default=True, nullable=False, server_default="true")

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
    preferred_channel = Column(Enum(NotificationChannel, values_callable=lambda e: [m.value for m in e], native_enum=False), default=NotificationChannel.SMS)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    clinic = relationship("Clinic", back_populates="patients")
    appointments = relationship("Appointment", back_populates="patient")

    __table_args__ = (
        Index("ix_patient_clinic_phone", "clinic_id", "phone"),
        # FIX: migration 014_patient_phone_unique added this constraint (the
        # conflict target for booking.py's INSERT ... ON CONFLICT upsert) but
        # the model never declared it — Base.metadata.create_all() (used for
        # SQLite tests) built a schema without it, and alembic autogenerate
        # would see it as an "unexpected" constraint to drop.
        UniqueConstraint("clinic_id", "phone", name="uq_patient_clinic_phone"),
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
    status = Column(Enum(AppointmentStatus, native_enum=False), nullable=False, default=AppointmentStatus.CONFIRMED, index=True)

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
    last_reminder_channel = Column(Enum(NotificationChannel, values_callable=lambda e: [m.value for m in e], native_enum=False))

    # Payment
    payment_required = Column(Boolean, default=False)
    payment_status = Column(Enum(PaymentStatus, native_enum=False), default=PaymentStatus.UNPAID)
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
        # Real backstop against concurrent double-booking: the application-level
        # SELECT ... FOR UPDATE check only locks rows that already exist, so two
        # concurrent requests booking the same still-empty slot both pass it and
        # both INSERT. This constraint makes the second INSERT fail with an
        # IntegrityError instead, which booking.py/appointments.py already catch
        # and turn into a clean 409. Excludes CANCELLED/NO_SHOW since a doctor can
        # have any number of those at the same slot over time.
        Index(
            "uq_doctor_slot",
            "doctor_id", "scheduled_at",
            unique=True,
            postgresql_where=text("status NOT IN ('CANCELLED', 'NO_SHOW')"),
            sqlite_where=text("status NOT IN ('CANCELLED', 'NO_SHOW')"),
        ),
    )


# ─── Patient Payments ─────────────────────────────────────────────────────────

class PatientPayment(Base):
    __tablename__ = "patient_payments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    appointment_id = Column(String(36), ForeignKey("appointments.id", ondelete="RESTRICT"), unique=True, nullable=False)
    clinic_id = Column(String(36), ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    provider = Column(Enum(PaymentProvider, native_enum=False), nullable=False)
    provider_reference = Column(String(255), unique=True, nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    clinic_share = Column(Numeric(12, 2), nullable=False)
    platform_share = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="NGN")
    status = Column(Enum(PaymentStatus, native_enum=False), default=PaymentStatus.PENDING)
    paid_at = Column(DateTime)
    extra_data = Column(JSONB, default={})
    created_at = Column(DateTime, default=func.now())

    appointment = relationship("Appointment", back_populates="payment_record")


class HospitalBankAccount(Base):
    __tablename__ = "hospital_bank_accounts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    hospital_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    account_number = Column(String(20), nullable=False)
    bank_code = Column(String(20), nullable=False)
    bank_name = Column(String(100), nullable=False)
    account_name = Column(String(255), nullable=False)
    paystack_recipient_code = Column(String(100))
    verified = Column(Boolean, default=False, nullable=False)
    active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    clinic = relationship("Clinic", back_populates="bank_accounts")

    __table_args__ = (
        Index("ix_hospital_bank_active", "hospital_id", "active"),
        # FIX: migration 018_bank_account_unique added this partial unique
        # index (the DB-level guarantee behind "one active account per
        # hospital") but the model never declared it — undeclared here, it
        # wasn't built by Base.metadata.create_all() and would look like an
        # unexpected object to alembic autogenerate.
        Index(
            "uq_hospital_bank_account_active",
            "hospital_id",
            unique=True,
            postgresql_where=text("active = true"),
            sqlite_where=text("active = 1"),
        ),
    )


class Payout(Base):
    __tablename__ = "payouts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    appointment_id = Column(String(36), ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False, unique=True)
    hospital_id = Column(String(36), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    status = Column(String(20), default=PayoutStatus.PENDING_PAYOUT.value, nullable=False, index=True)
    paystack_transfer_code = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime, default=func.now(), index=True)
    sent_at = Column(DateTime, nullable=True)

    appointment = relationship("Appointment")
    clinic = relationship("Clinic")

    __table_args__ = (
        Index("ix_payout_status_created", "status", "created_at"),
    )


# ─── Notifications ────────────────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    appointment_id = Column(String(36), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True)
    clinic_id = Column(String(36), ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)

    channel = Column(Enum(NotificationChannel, values_callable=lambda e: [m.value for m in e], native_enum=False), nullable=False)
    notification_type = Column(String(50), nullable=False)  # reminder | confirmation | cancellation | follow_up
    status = Column(Enum(NotificationStatus, native_enum=False), default=NotificationStatus.PENDING)

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
    whatsapp_enabled = Column(Boolean, default=True)
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


class PushSubscription(Base):
    """
    A single browser/PWA Web Push subscription for a clinic staff member.
    Table created by migration 011_push_subscriptions — this model class
    was the missing piece: the table existed in the DB, but nothing mapped
    to it, so every push subscribe/unsubscribe call and reminder task raised
    ImportError on `from app.models.models import PushSubscription`.
    """
    __tablename__ = "push_subscriptions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(String(64), nullable=False)
    user_agent = Column(String(512), nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


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


# ─── AI Core: Growth Agents (Lead Hunter / Sales / Content / Customer Success) ─
# Internal system powering Vitar's own growth toward its client-acquisition
# goal — not a customer-facing feature. See app/agents/ for the Celery task
# implementations and app/services/notifications.py + ai_provider.py for the
# shared infrastructure every agent below is built on.

class LeadSource(str, enum.Enum):
    GOOGLE_MAPS = "google_maps"
    LINKEDIN = "linkedin"
    DIRECTORY = "directory"
    MANUAL = "manual"


class LeadStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    REPLIED = "replied"
    TRIAL_STARTED = "trial_started"
    PAID = "paid"
    LOST = "lost"


class Lead(Base):
    __tablename__ = "leads"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    clinic_name = Column(String(255), nullable=False)
    phone = Column(String(20))
    email = Column(String(255))
    whatsapp = Column(String(20))
    address = Column(Text)
    city = Column(String(100))
    source = Column(Enum(LeadSource, native_enum=False), nullable=False)
    source_url = Column(Text)
    status = Column(Enum(LeadStatus, native_enum=False), nullable=False, default=LeadStatus.NEW)
    score = Column(Integer, nullable=False, default=0)
    notes = Column(Text)
    last_contacted_at = Column(DateTime)
    # How many times outreach has actually been SENT (not just drafted) to
    # this lead — see app/agents/sales_agent.py's 7-day cooldown and
    # auto-flip-to-lost-after-2-attempts logic.
    attempt_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Partial unique index on phone — the ON CONFLICT target for Lead
        # Hunter's upsert (see booking.py's patient upsert for the same
        # pattern). Partial (WHERE phone IS NOT NULL) because many scraped
        # listings have no phone at all.
        Index("uq_leads_phone", "phone", unique=True, postgresql_where=text("phone IS NOT NULL")),
        Index("ix_leads_status_score", "status", "score"),
    )


class ContentType(str, enum.Enum):
    SOCIAL_POST = "social_post"
    OUTREACH_TEMPLATE = "outreach_template"
    EMAIL = "email"


class ContentStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"


class ContentQueue(Base):
    __tablename__ = "content_queue"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    content_type = Column(Enum(ContentType, native_enum=False), nullable=False)
    body = Column(Text, nullable=False)
    target_platform = Column(String(50))
    status = Column(Enum(ContentStatus, native_enum=False), nullable=False, default=ContentStatus.DRAFT)
    created_by_agent = Column(String(50))
    approved_by = Column(String(36), ForeignKey("users.id"))
    created_at = Column(DateTime, default=func.now())
    published_at = Column(DateTime)
    # Links an outreach_template draft back to its lead (Phase 3's Sales
    # Agent). Nullable — Content Agent's social_post rows aren't lead-tied.
    lead_id = Column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_content_queue_status", "status"),
    )


class AgentRunStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class AgentRun(Base):
    """
    Run-history log every AI Core agent task writes to on every execution
    (see app/agents/utils.py's log_agent_run) — powers the superadmin
    dashboard's agent status dots and run history lists.
    """
    __tablename__ = "agent_runs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    agent_name = Column(String(50), nullable=False)
    task_name = Column(String(100), nullable=False)
    status = Column(Enum(AgentRunStatus, native_enum=False), nullable=False)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)
    items_processed = Column(Integer, nullable=False, default=0)
    items_created = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)

    __table_args__ = (
        Index("ix_agent_runs_name_started", "agent_name", "started_at"),
    )


class HealthSignalType(str, enum.Enum):
    LOW_USAGE = "low_usage"
    NO_LOGIN_7D = "no_login_7d"
    SUPPORT_FLAG = "support_flag"
    UPSELL_OPPORTUNITY = "upsell_opportunity"


class HealthSignalStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class CustomerHealthSignal(Base):
    __tablename__ = "customer_health_signals"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    clinic_id = Column(String(36), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    signal_type = Column(Enum(HealthSignalType, native_enum=False), nullable=False)
    detail = Column(Text)
    status = Column(Enum(HealthSignalStatus, native_enum=False), nullable=False, default=HealthSignalStatus.OPEN)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_health_signals_clinic_status", "clinic_id", "status"),
    )


class NotificationEventType(str, enum.Enum):
    LEADS_FOUND = "leads_found"
    OUTREACH_READY = "outreach_ready"
    LEAD_REPLIED = "lead_replied"
    LEAD_TRIAL_STARTED = "lead_trial_started"
    CONTENT_READY = "content_ready"
    HEALTH_SIGNAL = "health_signal"
    AGENT_FAILED = "agent_failed"
    SUBSCRIPTION_PAID = "subscription_paid"
    SUBSCRIPTION_OVERRIDE = "subscription_override"
    APPOINTMENT_REFUND_NEEDED = "appointment_refund_needed"
    PAYOUT_BLOCKED_NO_BANK = "payout_blocked_no_bank"
    BOOKING_PAYMENT_RECEIVED = "booking_payment_received"
    PAYOUT_SENT = "payout_sent"


class AgentNotification(Base):
    """
    Shared notification feed for the AI Core agents — the single source of
    truth both the superadmin dashboard's notification center (Phase 6) and
    the Telegram bot (Phase 7) read from independently. Every agent writes
    here exactly once per event via app/services/notifications.py's notify()
    — neither consumer triggers the other, so they can never show
    conflicting unread state.

    Named agent_notifications, NOT notifications — that table name is
    already taken by the Notification model above (patient-facing SMS/
    WhatsApp/email delivery tracking, a completely different concept: that
    one is customer communication history, this one is an internal ops
    alert feed).
    """
    __tablename__ = "agent_notifications"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    event_type = Column(Enum(NotificationEventType, native_enum=False), nullable=False)
    agent_name = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    related_id = Column(String(36))  # points at a lead/content/signal row; no FK — the target table varies by event_type
    link_path = Column(Text)
    is_read = Column(Boolean, nullable=False, default=False)
    # Separate from is_read on purpose — "the Telegram bot already sent
    # this" and "an admin has seen the dashboard bell" are different facts;
    # conflating them would make the bot pushing a notification silently
    # mark it read for the dashboard too.
    pushed_to_telegram = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_agent_notifications_is_read", "is_read"),
        Index("ix_agent_notifications_created_at", "created_at"),
        Index("ix_agent_notifications_pushed", "pushed_to_telegram"),
    )


class AiUsageLog(Base):
    """Token usage per AI Core call, logged by app/services/ai_provider.py's
    generate() — lets you track AI spend per agent over time."""
    __tablename__ = "ai_usage_log"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    timestamp = Column(DateTime, default=func.now())
    agent_name = Column(String(50), nullable=False)
    tokens_used = Column(Integer, nullable=False, default=0)
    model = Column(String(100))
