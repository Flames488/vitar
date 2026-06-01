"""Vitar v5 - Clinics Endpoint"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_clinic
from app.services.trial_guard import get_trial_status

router = APIRouter()

class ClinicUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    website: Optional[str] = None
    timezone: Optional[str] = None
    booking_page_enabled: Optional[bool] = None
    online_booking_enabled: Optional[bool] = None
    consultation_fee: Optional[float] = None

@router.get("/me")
def get_clinic(clinic=Depends(get_current_clinic)):
    trial = get_trial_status(clinic)
    return {
        "id": clinic.id,
        "name": clinic.name,
        "slug": clinic.slug,
        "email": clinic.email,
        "phone": clinic.phone,
        "address": clinic.address,
        "city": clinic.city,
        "state": clinic.state,
        "country": clinic.country,
        "currency": clinic.currency,
        "timezone": clinic.timezone,
        "logo_url": clinic.logo_url,
        "website": clinic.website,
        "booking_page_enabled": clinic.booking_page_enabled,
        "online_booking_enabled": clinic.online_booking_enabled,
        "consultation_fee": float(clinic.consultation_fee) if clinic.consultation_fee else 0,
        "patient_payment_enabled": clinic.patient_payment_enabled,
        "onboarding_completed": clinic.onboarding_completed,
        "onboarding_step": clinic.onboarding_step,
        "trial": trial,
    }

@router.patch("/me")
def update_clinic(
    body: ClinicUpdate,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(clinic, field, val)
    db.commit()
    db.refresh(clinic)
    return {"message": "Clinic updated", "id": clinic.id}
