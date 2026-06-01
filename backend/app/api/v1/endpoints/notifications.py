"""
Vitar v5 - Notifications Settings Endpoint
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_clinic
from app.models.models import NotificationSettings

router = APIRouter()

class NotificationSettingsUpdate(BaseModel):
    sms_enabled: Optional[bool] = None
    whatsapp_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    reminder_hours_before: Optional[int] = None
    second_reminder_hours: Optional[int] = None
    ai_smart_reminders: Optional[bool] = None
    high_risk_extra_reminder: Optional[bool] = None
    sms_sender_name: Optional[str] = None
    custom_reminder_message: Optional[str] = None

@router.get("/")
def get_notification_settings(
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    ns = db.query(NotificationSettings).filter(NotificationSettings.clinic_id == clinic.id).first()
    if not ns:
        raise HTTPException(status_code=404, detail="Notification settings not found")
    return {
        "sms_enabled": ns.sms_enabled,
        "whatsapp_enabled": ns.whatsapp_enabled,
        "email_enabled": ns.email_enabled,
        "reminder_hours_before": ns.reminder_hours_before,
        "second_reminder_hours": ns.second_reminder_hours,
        "ai_smart_reminders": ns.ai_smart_reminders,
        "high_risk_extra_reminder": ns.high_risk_extra_reminder,
        "sms_sender_name": ns.sms_sender_name,
        "custom_reminder_message": ns.custom_reminder_message,
    }

@router.patch("/")
def update_notification_settings(
    body: NotificationSettingsUpdate,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    ns = db.query(NotificationSettings).filter(NotificationSettings.clinic_id == clinic.id).first()
    if not ns:
        raise HTTPException(status_code=404, detail="Notification settings not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(ns, field, val)
    db.commit()
    return {"message": "Settings updated"}
