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
    # Bank transfer payment settings
    patient_payment_enabled: Optional[bool] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None

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
        # Bank transfer fields (stored as paystack_* columns, repurposed for direct transfer)
        "bank_name": clinic.paystack_bank_name,
        "account_number": clinic.paystack_account_number,
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
    data = body.model_dump(exclude_none=True)

    # Map frontend field names to model column names
    field_map = {
        "bank_name": "paystack_bank_name",
        "account_number": "paystack_account_number",
    }

    for field, val in data.items():
        model_field = field_map.get(field, field)
        setattr(clinic, model_field, val)

    db.commit()
    db.refresh(clinic)
    return {"message": "Clinic updated", "id": clinic.id}
