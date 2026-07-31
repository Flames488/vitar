"""
Vitar — Admin API Key Management Endpoints

GET  /api/v1/admin/api-keys         List all keys (no hashes)
POST /api/v1/admin/api-keys         Generate new key (returns raw once)
DELETE /api/v1/admin/api-keys/{id}  Revoke a key

These manage the single platform-wide integration key (ApiKey has no
clinic_id — see app/middleware/api_key_auth.py), so they require superadmin
auth, not clinic admin auth. A clinic owner must never be able to mint or
revoke this key.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_superadmin
from app.models.api_key import ApiKey

router = APIRouter(prefix="/admin/api-keys", tags=["admin-api-keys"])


class GenerateKeyRequest(BaseModel):
    label: str


@router.get("/")
def list_api_keys(
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    """List all API keys for the clinic. Raw hashes are never returned."""
    keys = db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()
    return [
        {
            "id": str(k.id),
            "label": k.label,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat(),
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in keys
    ]


@router.post("/", status_code=201)
def generate_api_key(
    body: GenerateKeyRequest,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    """
    Generate a new API key.  The raw key is returned ONCE in this response.
    It is never retrievable again — only the bcrypt hash is stored.
    """
    if not body.label.strip():
        raise HTTPException(status_code=422, detail="Label is required")

    api_key_obj, raw_key = ApiKey.generate(label=body.label.strip())
    db.add(api_key_obj)
    db.commit()
    db.refresh(api_key_obj)

    return {
        "id": str(api_key_obj.id),
        "label": api_key_obj.label,
        "raw_key": raw_key,   # Only exposed here — store immediately
        "created_at": api_key_obj.created_at.isoformat(),
    }


@router.delete("/{key_id}", status_code=204)
def revoke_api_key(
    key_id: str,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    """Revoke an API key by setting is_active = false."""
    key_obj = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not key_obj:
        raise HTTPException(status_code=404, detail="API key not found")
    if not key_obj.is_active:
        raise HTTPException(status_code=409, detail="Key already revoked")

    key_obj.revoke()
    db.commit()
    return None
