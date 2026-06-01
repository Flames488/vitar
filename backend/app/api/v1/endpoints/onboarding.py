"""Vitar v5 - Onboarding Endpoint"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_clinic

router = APIRouter()

class OnboardingStep(BaseModel):
    step: int
    data: Optional[dict] = {}

@router.get("/status")
def onboarding_status(clinic=Depends(get_current_clinic)):
    return {
        "completed": clinic.onboarding_completed,
        "step": clinic.onboarding_step,
        "steps": [
            {"id": 1, "title": "Clinic Profile", "done": clinic.onboarding_step > 1},
            {"id": 2, "title": "Add First Doctor", "done": clinic.onboarding_step > 2},
            {"id": 3, "title": "Set Availability", "done": clinic.onboarding_step > 3},
            {"id": 4, "title": "Notification Setup", "done": clinic.onboarding_step > 4},
            {"id": 5, "title": "Test Booking", "done": clinic.onboarding_step > 5},
        ],
    }

@router.post("/complete-step")
def complete_step(
    body: OnboardingStep,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    if body.step > (clinic.onboarding_step or 0):
        clinic.onboarding_step = body.step
    if body.step >= 5:
        clinic.onboarding_completed = True
    db.commit()
    return {"step": clinic.onboarding_step, "completed": clinic.onboarding_completed}
