"""
Vitar v5 - API v1 Router
Aggregates all sub-routers
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    clinics,
    doctors,
    patients,
    appointments,
    booking,
    notifications,
    billing,
    analytics,
    ai,
    webhooks,
    geo,
    onboarding,
    waiting_list,
    uploads,
    admin_api_keys,
    admin_users,
    admin_clinics,
    admin_subscriptions,
    admin_analytics,
    admin_audit,
    qr,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(clinics.router, prefix="/clinics", tags=["Clinics"])
api_router.include_router(doctors.router, prefix="/doctors", tags=["Doctors"])
api_router.include_router(patients.router, prefix="/patients", tags=["Patients"])
api_router.include_router(appointments.router, prefix="/appointments", tags=["Appointments"])
api_router.include_router(booking.router, prefix="/booking", tags=["Public Booking"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(billing.router, prefix="/billing", tags=["Billing"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI Features"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(geo.router, prefix="/geo", tags=["Geo / Currency"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["Onboarding"])
api_router.include_router(waiting_list.router, prefix="/waiting-list", tags=["Waiting List"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["File Uploads"])
api_router.include_router(admin_api_keys.router, tags=["Admin — API Keys"])
api_router.include_router(qr.router, prefix="/qr", tags=["QR Code"])

# ── Superadmin Dashboard (/admin/*) ────────────────────────────────────────
# Each router below is independently protected by get_current_superadmin
# (app/core/security.py) — never trust the frontend route guard alone.
api_router.include_router(admin_users.router, tags=["Admin — Users"])
api_router.include_router(admin_clinics.router, tags=["Admin — Clinics"])
api_router.include_router(admin_subscriptions.router, tags=["Admin — Subscriptions"])
api_router.include_router(admin_analytics.router, tags=["Admin — Analytics"])
api_router.include_router(admin_audit.router, tags=["Admin — Audit Log"])
