"""
Vitar v11 — Auth Endpoints
Adds:
  1. httpOnly SameSite=Strict cookie auth (replaces localStorage)
  2. CSRF double-submit protection
  3. Refresh token revocation (DB-stored hash, rotate-on-use)
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Response, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
import secrets
import hashlib

from app.core.utils import utcnow
from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, generate_secure_token,
    get_current_user,
)
from app.core.config import settings
from app.core.cookie_auth import (
    set_auth_cookies, clear_auth_cookies,
    get_refresh_token_from_cookie,
)
from app.models.models import User, Clinic, Subscription, NotificationSettings
from app.models.models import (
    SubscriptionPlan, SubscriptionStatus, Region, RefreshToken,
)
from app.services.email_service import send_welcome_email, send_password_reset_email
from app.services.qr_service import generate_clinic_qr

router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    phone: str
    clinic_name: str
    city: str
    country: str = "NG"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    is_superadmin: bool = False

class ClinicOut(BaseModel):
    id: str
    name: str
    slug: str
    country: str
    currency: str
    trial_ends_at: str | None
    onboarding_completed: bool
    onboarding_step: int

class AuthResponse(BaseModel):
    """
    v11: No tokens in body — they live in httpOnly cookies.
    The csrf_token IS returned in the body so the frontend can
    bootstrap its CSRF header without a separate request.

    v12: clinic is now Optional — superadmin-only accounts (created via
    scripts/create_superadmin.py) have no clinic of their own and must
    still be able to log in to access the /admin dashboard.
    """
    csrf_token: str
    user: UserOut
    clinic: ClinicOut | None = None


# ─── Refresh token helpers ────────────────────────────────────────────────────

def _hash_token(token: str) -> str:
    """SHA-256 hash of a token. We store the hash, never the raw token."""
    return hashlib.sha256(token.encode()).hexdigest()


def _store_refresh_token(user_id: str, token: str, db: Session) -> None:
    """Persist a hashed refresh token. Replaces any existing token for this user."""
    # Revoke all existing refresh tokens for this user (single-session)
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()
    rt = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(token),
        expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(rt)


def _revoke_refresh_token(user_id: str, db: Session) -> None:
    """Delete all refresh tokens for a user (logout / password change)."""
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()


def _validate_refresh_token(token: str, db: Session) -> RefreshToken:
    """
    Look up the token hash in the DB.
    Raises 401 if not found, expired, or already used (hash mismatch).
    """
    token_hash = _hash_token(token)
    rt = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
    ).first()

    if not rt:
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")

    if rt.expires_at and utcnow() > rt.expires_at:
        db.delete(rt)
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    return rt


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _generate_slug(clinic_name: str, db: Session) -> str:
    import re
    base = re.sub(r"[^a-z0-9]+", "-", clinic_name.lower()).strip("-")
    slug = base
    counter = 1
    while db.query(Clinic).filter(Clinic.slug == slug).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def _create_default_notification_settings(clinic_id: str, db: Session):
    s = NotificationSettings(
        clinic_id=clinic_id,
        sms_enabled=True,
        email_enabled=True,
        reminder_hours_before=24,
        second_reminder_hours=2,
        ai_smart_reminders=True,
        high_risk_extra_reminder=True,
    )
    db.add(s)


def _determine_region(country: str) -> Region:
    return {"NG": Region.NG, "US": Region.US, "GB": Region.UK}.get(
        country.upper(), Region.OTHER
    )


def _clinic_dict(clinic: Clinic) -> dict:
    now = utcnow()
    trial_ends_at = clinic.trial_ends_at
    is_on_trial = trial_ends_at is not None
    is_expired = is_on_trial and now > trial_ends_at
    days_left = max(0, (trial_ends_at - now).days) if is_on_trial and not is_expired else 0
    bookings_used = clinic.trial_bookings_used or 0
    bookings_limit = settings.TRIAL_MAX_BOOKINGS

    return {
        "id": clinic.id,
        "name": clinic.name,
        "slug": clinic.slug,
        "trial_ends_at": trial_ends_at.isoformat() if trial_ends_at else None,
        "country": clinic.country,
        "currency": clinic.currency,
        "onboarding_completed": clinic.onboarding_completed,
        "onboarding_step": clinic.onboarding_step,
        "trial": {
            "is_trial": is_on_trial,
            "is_expired": is_expired,
            "days_left": days_left,
            "bookings_used": bookings_used,
            "bookings_limit": bookings_limit,
            "show_upgrade_nudge": is_on_trial and (is_expired or days_left <= 7),
        } if is_on_trial else None,
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    if not any(c.isdigit() for c in body.password):
        raise HTTPException(422, "Password must contain at least one number")
    if not any(c.isupper() for c in body.password):
        raise HTTPException(422, "Password must contain at least one uppercase letter")

    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "Email already registered")

    user = User(
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        phone=body.phone,
        is_active=True,
        is_verified=False,
        email_verification_token=generate_secure_token(),
    )
    db.add(user)
    db.commit()        # commit user first so FK is visible across all connections
    db.refresh(user)   # re-attach user to session after commit

    trial_ends = utcnow() + timedelta(days=settings.TRIAL_DAYS)
    region = _determine_region(body.country)
    currency = "NGN" if body.country == "NG" else "USD"

    clinic = Clinic(
        owner_id=user.id,
        name=body.clinic_name,
        slug=_generate_slug(body.clinic_name, db),
        email=body.email.lower(),
        phone=body.phone,
        city=body.city,
        country=body.country.upper(),
        region=region,
        currency=currency,
        trial_started_at=utcnow(),
        trial_ends_at=trial_ends,
        is_active=True,
        onboarding_completed=False,
        onboarding_step=1,
    )
    db.add(clinic)
    db.commit()        # commit clinic so FK is visible for subscription + notification_settings
    db.refresh(clinic)

    db.add(Subscription(
        clinic_id=clinic.id,
        plan=SubscriptionPlan.TRIAL,
        status=SubscriptionStatus.TRIALING,
        current_period_start=utcnow(),
        current_period_end=trial_ends,
        amount=0,
        currency=currency,
    ))
    _create_default_notification_settings(clinic.id, db)

    # Generate tokens and store refresh hash
    access_token  = create_access_token({"sub": user.id, "clinic_id": clinic.id})
    refresh_token = create_refresh_token({"sub": user.id})
    _store_refresh_token(user.id, refresh_token, db)

    db.commit()  # commit subscription, notification_settings, refresh_token together

    # Generate QR code immediately at registration so it exists from day one.
    # The lazy /qr/me approach meant clinics that never visited QR settings had
    # no QR code at all — breaking any printed/physical collateral.
    try:
        qr_path = generate_clinic_qr(clinic)
        clinic.qr_code_path = qr_path
        db.commit()
    except Exception as qr_err:
        # Non-fatal — registration succeeds even if QR generation fails.
        # The lazy /qr/me endpoint will generate it on first dashboard visit.
        import logging
        logging.getLogger(__name__).warning(f"QR generation failed at registration for {clinic.id}: {qr_err}")

    background_tasks.add_task(send_welcome_email, user.email, user.full_name, clinic.name)

    csrf_token = set_auth_cookies(response, access_token, refresh_token)

    return {
        "csrf_token": csrf_token,
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "is_superadmin": user.is_superadmin},
        "clinic": _clinic_dict(clinic),
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(
        User.email == body.email.lower(), User.is_active == True
    ).first()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")

    clinic = db.query(Clinic).filter(
        Clinic.owner_id == user.id, Clinic.is_active == True
    ).first()
    # v12 FIX: superadmin-only accounts (no clinic of their own, e.g. bootstrapped
    # via scripts/create_superadmin.py) must still be able to log in — they need
    # access to /admin, not a clinic dashboard. Regular users still require a clinic.
    if not clinic and not user.is_superadmin:
        raise HTTPException(404, "No clinic found for this account")

    user.last_login_at = utcnow()

    access_token  = create_access_token({"sub": user.id, "clinic_id": clinic.id if clinic else None})
    refresh_token = create_refresh_token({"sub": user.id})
    _store_refresh_token(user.id, refresh_token, db)
    db.commit()

    csrf_token = set_auth_cookies(response, access_token, refresh_token)

    return {
        "csrf_token": csrf_token,
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "is_superadmin": user.is_superadmin},
        "clinic": _clinic_dict(clinic) if clinic else None,
    }


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    v12: Session-restore endpoint that works for BOTH clinic owners and
    superadmin-only accounts. The frontend uses this on app mount instead of
    GET /clinics/me, which 404s for users without a clinic.
    """
    clinic = db.query(Clinic).filter(
        Clinic.owner_id == current_user.id, Clinic.is_active == True
    ).first()
    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "is_superadmin": current_user.is_superadmin,
        },
        "clinic": _clinic_dict(clinic) if clinic else None,
    }


@router.post("/refresh")
async def refresh_token_endpoint(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Rotate refresh token:
      1. Read token from httpOnly cookie (not request body)
      2. Validate against DB hash (single-use: old token revoked immediately)
      3. Issue new access + refresh tokens and set fresh cookies
    """
    raw_refresh = get_refresh_token_from_cookie(request)
    if not raw_refresh:
        raise HTTPException(401, "No refresh token")

    # Validate JWT signature + expiry first (fast check)
    payload = decode_token(raw_refresh)
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Invalid token type")

    user_id = payload.get("sub")

    # Validate against DB (revocation check)
    rt = _validate_refresh_token(raw_refresh, db)

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(401, "User not found")

    clinic = db.query(Clinic).filter(Clinic.owner_id == user.id).first()

    # Revoke old token and issue new pair (rotate)
    db.delete(rt)
    new_access  = create_access_token({"sub": user.id, "clinic_id": clinic.id if clinic else None})
    new_refresh = create_refresh_token({"sub": user.id})
    _store_refresh_token(user.id, new_refresh, db)
    db.commit()

    csrf_token = set_auth_cookies(response, new_access, new_refresh)
    return {"csrf_token": csrf_token}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Revoke refresh token in DB and clear all cookies.
    Best-effort: always returns 200 even if the token wasn't in DB.
    """
    raw_refresh = get_refresh_token_from_cookie(request)
    if raw_refresh:
        try:
            payload = decode_token(raw_refresh)
            user_id = payload.get("sub")
            if user_id:
                _revoke_refresh_token(user_id, db)
                db.commit()
        except Exception:
            pass  # Expired token on logout is fine — just clear cookies

    clear_auth_cookies(response)
    return {"message": "Logged out"}


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user:
        token = generate_secure_token()
        user.password_reset_token = token
        user.password_reset_expires = utcnow() + timedelta(hours=1)
        db.commit()
        background_tasks.add_task(
            send_password_reset_email, user.email, token, settings.FRONTEND_URL
        )
    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    if len(body.new_password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    if not any(c.isdigit() for c in body.new_password):
        raise HTTPException(422, "Password must contain at least one number")
    if not any(c.isupper() for c in body.new_password):
        raise HTTPException(422, "Password must contain at least one uppercase letter")

    user = db.query(User).filter(
        User.password_reset_token == body.token,
    ).first()

    if not user or not user.password_reset_expires:
        raise HTTPException(400, "Invalid or expired token")
    if utcnow() > user.password_reset_expires:
        raise HTTPException(400, "Reset token has expired")

    user.hashed_password = hash_password(body.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None

    # Revoke all refresh tokens on password change
    _revoke_refresh_token(user.id, db)
    db.commit()

    # Clear auth cookies (force re-login)
    clear_auth_cookies(response)
    return {"message": "Password updated. Please log in again."}
