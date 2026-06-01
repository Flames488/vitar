"""Vitar v5 - Waiting List Endpoint"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_clinic
from app.models.models import WaitingList

router = APIRouter()

@router.get("/")
def list_waiting(clinic=Depends(get_current_clinic), db: Session = Depends(get_db)):
    entries = db.query(WaitingList).filter(
        WaitingList.clinic_id == clinic.id,
        WaitingList.status == "waiting",
    ).order_by(WaitingList.created_at).all()
    return {"items": [
        {
            "id": e.id,
            "patient_name": e.patient_name,
            "patient_phone": e.patient_phone,
            "doctor_id": e.doctor_id,
            "preferred_date": e.preferred_date.isoformat() if e.preferred_date else None,
            "status": e.status,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]}

@router.delete("/{entry_id}")
def remove_from_waitlist(entry_id: str, clinic=Depends(get_current_clinic), db: Session = Depends(get_db)):
    e = db.query(WaitingList).filter(WaitingList.id == entry_id, WaitingList.clinic_id == clinic.id).first()
    if e:
        e.status = "removed"
        db.commit()
    return {"message": "Removed"}
