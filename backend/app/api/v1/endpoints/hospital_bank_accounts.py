from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_clinic
from app.models.models import Clinic, HospitalBankAccount
from app.services.hospital_payments import hospital_payments


router = APIRouter()


class BankAccountRequest(BaseModel):
    account_number: str = Field(..., min_length=10, max_length=10)
    bank_code: str


def _serialize(account: HospitalBankAccount | None) -> dict | None:
    if not account:
        return None
    return {
        "id": account.id,
        "hospital_id": account.hospital_id,
        "account_number": account.account_number,
        "bank_code": account.bank_code,
        "bank_name": account.bank_name,
        "account_name": account.account_name,
        "paystack_recipient_code": account.paystack_recipient_code,
        "verified": bool(account.verified),
        "active": bool(account.active),
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


async def _create_account(clinic: Clinic, body: BankAccountRequest, db: Session) -> HospitalBankAccount:
    if clinic.country != "NG":
        raise HTTPException(status_code=400, detail="Bank payouts are currently available for Nigerian hospitals only")

    banks = await hospital_payments.get_banks()
    bank = next((b for b in banks if b["code"] == body.bank_code), None)
    if not bank:
        raise HTTPException(status_code=400, detail="Unsupported bank code")

    try:
        resolved = await hospital_payments.resolve_account(body.account_number, body.bank_code)
        recipient = await hospital_payments.create_transfer_recipient(
            business_name=clinic.name,
            account_number=body.account_number,
            bank_code=body.bank_code,
        )
    except Exception:
        raise HTTPException(status_code=502, detail="Unable to verify bank account with Paystack")

    account = HospitalBankAccount(
        hospital_id=clinic.id,
        account_number=body.account_number,
        bank_code=body.bank_code,
        bank_name=bank["name"],
        account_name=resolved.get("account_name", ""),
        paystack_recipient_code=recipient.get("recipient_code"),
        verified=True,
        active=True,
    )
    db.add(account)
    return account


@router.get("/banks")
async def list_banks(clinic=Depends(get_current_clinic)):
    if clinic.country != "NG":
        return {"banks": []}
    return {"banks": await hospital_payments.get_banks()}


@router.post("/hospitals/{hospital_id}/bank-account/resolve")
async def resolve_bank_account(
    hospital_id: str,
    body: BankAccountRequest,
    clinic=Depends(get_current_clinic),
):
    if str(clinic.id) != hospital_id:
        raise HTTPException(status_code=403, detail="Cannot resolve another hospital's bank account")
    banks = await hospital_payments.get_banks()
    bank = next((b for b in banks if b["code"] == body.bank_code), None)
    if not bank:
        raise HTTPException(status_code=400, detail="Unsupported bank code")
    try:
        resolved = await hospital_payments.resolve_account(body.account_number, body.bank_code)
    except Exception:
        raise HTTPException(status_code=502, detail="Unable to verify bank account with Paystack")
    return {
        "account_number": body.account_number,
        "bank_code": body.bank_code,
        "bank_name": bank["name"],
        "account_name": resolved.get("account_name", ""),
    }


@router.get("/hospitals/{hospital_id}/bank-account")
def get_bank_account(
    hospital_id: str,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    if str(clinic.id) != hospital_id:
        raise HTTPException(status_code=403, detail="Cannot access another hospital's bank account")
    account = db.query(HospitalBankAccount).filter(
        HospitalBankAccount.hospital_id == hospital_id,
        HospitalBankAccount.active == True,  # noqa: E712
    ).order_by(HospitalBankAccount.created_at.desc()).first()
    return {"bank_account": _serialize(account)}


@router.post("/hospitals/{hospital_id}/bank-account", status_code=201)
async def create_bank_account(
    hospital_id: str,
    body: BankAccountRequest,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    if str(clinic.id) != hospital_id:
        raise HTTPException(status_code=403, detail="Cannot configure another hospital's bank account")
    existing = db.query(HospitalBankAccount).filter(
        HospitalBankAccount.hospital_id == hospital_id,
        HospitalBankAccount.active == True,  # noqa: E712
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Bank account already exists; use PUT to replace it")
    account = await _create_account(clinic, body, db)
    db.commit()
    db.refresh(account)
    return {"bank_account": _serialize(account)}


@router.put("/hospitals/{hospital_id}/bank-account")
async def replace_bank_account(
    hospital_id: str,
    body: BankAccountRequest,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    if str(clinic.id) != hospital_id:
        raise HTTPException(status_code=403, detail="Cannot configure another hospital's bank account")
    existing = db.query(HospitalBankAccount).filter(
        HospitalBankAccount.hospital_id == hospital_id,
        HospitalBankAccount.active == True,  # noqa: E712
    ).all()
    for row in existing:
        row.active = False
    account = await _create_account(clinic, body, db)
    db.commit()
    db.refresh(account)
    return {"bank_account": _serialize(account)}
