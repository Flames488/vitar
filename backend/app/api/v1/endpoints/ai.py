"""
Vitar v5 - AI Endpoints
No-show prediction, smart reminder engine, risk analytics, chatbot.

Chatbot backend: Groq (llama-3.3-70b-versatile) — free tier available,
fast inference, no per-token billing surprises.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from app.core.utils import utcnow
from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_clinic
from app.core.logging import get_logger
from app.models.models import Appointment, Patient, NoShowPrediction, AppointmentStatus
from app.services.ai_service import NoShowPredictor, calculate_risk_category

router = APIRouter()
predictor = NoShowPredictor()
logger = get_logger(__name__)


# ─── Schemas ──────────────────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    appointment_id: str


class ChatMessage(BaseModel):
    role: str       # "user" or "assistant" only
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[ChatMessage]] = []


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/risk-dashboard")
def risk_dashboard(
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """
    Returns upcoming appointments sorted by no-show risk.
    Shows risk distribution and high-risk patient list.
    """
    upcoming = db.query(Appointment).filter(
        Appointment.clinic_id == clinic.id,
        Appointment.status == AppointmentStatus.CONFIRMED,
        Appointment.scheduled_at > utcnow(),
    ).order_by(Appointment.scheduled_at).all()

    risk_buckets = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    high_risk_appointments = []

    for apt in upcoming:
        score = apt.no_show_risk_score or 0.0
        category = calculate_risk_category(score)
        risk_buckets[category] += 1

        if category in ("high", "critical"):
            high_risk_appointments.append({
                "id": apt.id,
                "scheduled_at": apt.scheduled_at.isoformat(),
                "risk_score": round(score, 3),
                "risk_category": category,
                "risk_factors": apt.risk_factors or {},
                "patient": {
                    "id": apt.patient_id,
                    "name": apt.patient.full_name if apt.patient else "Unknown",
                    "phone": apt.patient.phone if apt.patient else "",
                    "historical_no_show_rate": apt.patient.historical_no_show_rate if apt.patient else 0,
                },
                "reminder_count": apt.reminder_count,
            })

    high_risk_appointments.sort(key=lambda x: x["risk_score"], reverse=True)

    total_appointments = db.query(Appointment).filter(
        Appointment.clinic_id == clinic.id
    ).count()

    total_no_shows = db.query(Appointment).filter(
        Appointment.clinic_id == clinic.id,
        Appointment.status == AppointmentStatus.NO_SHOW,
    ).count()

    overall_no_show_rate = (total_no_shows / total_appointments * 100) if total_appointments > 0 else 0

    return {
        "upcoming_total": len(upcoming),
        "risk_distribution": risk_buckets,
        "high_risk_appointments": high_risk_appointments[:20],
        "clinic_stats": {
            "total_appointments": total_appointments,
            "total_no_shows": total_no_shows,
            "no_show_rate_percent": round(overall_no_show_rate, 1),
            "estimated_reduction_percent": 40,
        },
    }


@router.post("/predict/{appointment_id}")
def predict_no_show(
    appointment_id: str,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """Run/re-run no-show prediction for a specific appointment."""
    apt = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.clinic_id == clinic.id,
    ).first()

    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    patient = db.query(Patient).filter(Patient.id == apt.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    features, score = predictor.predict(apt, patient, db)
    category = calculate_risk_category(score)

    apt.no_show_risk_score = score
    apt.risk_factors = features
    apt.risk_calculated_at = utcnow()

    prediction_record = NoShowPrediction(
        appointment_id=apt.id,
        patient_id=patient.id,
        model_version=predictor.version,
        risk_score=score,
        risk_category=category,
        features=features,
    )
    db.add(prediction_record)
    db.commit()

    return {
        "appointment_id": appointment_id,
        "risk_score": round(score, 4),
        "risk_category": category,
        "risk_factors": features,
        "recommended_action": _get_recommended_action(category, apt.reminder_count),
    }


@router.get("/no-show-trends")
def no_show_trends(
    months: int = 6,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """Monthly no-show trend data for charting."""
    from sqlalchemy import extract

    cutoff = utcnow().replace(day=1)
    results = []

    for i in range(months - 1, -1, -1):
        month = cutoff.month - i
        year = cutoff.year
        while month <= 0:
            month += 12
            year -= 1

        total = db.query(Appointment).filter(
            Appointment.clinic_id == clinic.id,
            extract("year", Appointment.scheduled_at) == year,
            extract("month", Appointment.scheduled_at) == month,
            Appointment.status.in_([
                AppointmentStatus.COMPLETED,
                AppointmentStatus.NO_SHOW,
                AppointmentStatus.CONFIRMED,
            ]),
        ).count()

        no_shows = db.query(Appointment).filter(
            Appointment.clinic_id == clinic.id,
            extract("year", Appointment.scheduled_at) == year,
            extract("month", Appointment.scheduled_at) == month,
            Appointment.status == AppointmentStatus.NO_SHOW,
        ).count()

        rate = (no_shows / total * 100) if total > 0 else 0

        results.append({
            "month": f"{year}-{month:02d}",
            "total": total,
            "no_shows": no_shows,
            "rate": round(rate, 1),
        })

    return {"trends": results}


@router.post("/chatbot")
async def ai_chatbot(
    body: ChatRequest,
    clinic=Depends(get_current_clinic),
):
    """
    AI assistant for clinic staff.
    Provider: Groq (llama-3.3-70b-versatile) — fast, free tier.
    """
    if not settings.GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI chatbot not configured. Please set GROQ_API_KEY in your environment.",
        )

    SYSTEM_PROMPT = (
        "You are Vitar Assistant, a helpful AI for healthcare clinic staff. "
        "You help with:\n"
        "- Booking and managing appointments\n"
        "- Understanding no-show risk scores\n"
        "- Navigating the Vitar dashboard\n"
        "- Billing and subscription questions\n"
        "- Best practices to reduce patient no-shows\n\n"
        "Keep answers concise and practical. If unsure, say so honestly.\n"
        f"Clinic context: {clinic.name}"
    )

    # Sanitise history: only allow 'user' and 'assistant' roles.
    # Never allow 'system' from client — that's a prompt-injection vector.
    safe_history = [
        {"role": msg.role, "content": msg.content}
        for msg in (body.conversation_history or [])
        if msg.role in ("user", "assistant") and msg.content.strip()
    ][-20:]  # Cap at last 20 turns to stay within context window

    messages = safe_history + [{"role": "user", "content": body.message}]

    try:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        completion = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            max_tokens=600,
            temperature=0.4,
        )
        reply = completion.choices[0].message.content or "I'm unable to respond right now."

    except Exception as e:
        logger.error(f"Groq chatbot error: {e}")
        reply = "I'm temporarily unavailable. Please check the Help section or contact support."

    return {
        "reply": reply,
        "conversation_history": messages + [{"role": "assistant", "content": reply}],
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_recommended_action(category: str, reminder_count: int) -> str:
    actions = {
        "low": "Standard reminder 24h before appointment.",
        "medium": "Send reminder 24h and 2h before. Monitor.",
        "high": "Send immediate reminder + 24h + 2h. Consider phone call.",
        "critical": "Call patient now. Send SMS + WhatsApp. Flag for rescheduling if no response.",
    }
    return actions.get(category, "Standard reminder protocol.")
