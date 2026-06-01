"""
Vitar v8 — Unified Response Models

Enforces consistent API response shapes across all endpoints.
Eliminates silent schema drift that breaks the frontend.

Usage:
    from app.core.response_models import ok, err, paginated

    # Success
    return ok(data={"appointment_id": "abc"})

    # Error (use instead of raising HTTPException in services)
    return err("Slot already booked", code="DOUBLE_BOOKING", status=409)

    # Paginated list
    return paginated(items=rows, total=total, page=page, page_size=size)
"""

from typing import Any, Optional, Generic, TypeVar, List
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

T = TypeVar("T")


class SuccessEnvelope(BaseModel):
    success: bool = True
    data: Any
    meta: Optional[dict] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ErrorEnvelope(BaseModel):
    success: bool = False
    error: str
    code: Optional[str] = None
    detail: Optional[Any] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PaginatedEnvelope(BaseModel):
    success: bool = True
    data: List[Any]
    pagination: dict
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def ok(data: Any, meta: Optional[dict] = None, status_code: int = 200) -> JSONResponse:
    """Return a successful JSON response."""
    body = SuccessEnvelope(data=data, meta=meta)
    return JSONResponse(content=body.model_dump(), status_code=status_code)


def err(
    message: str,
    code: Optional[str] = None,
    detail: Optional[Any] = None,
    status: int = 400,
) -> JSONResponse:
    """Return a structured error response."""
    body = ErrorEnvelope(error=message, code=code, detail=detail)
    return JSONResponse(content=body.model_dump(), status_code=status)


def paginated(
    items: List[Any],
    total: int,
    page: int,
    page_size: int,
) -> JSONResponse:
    """Return a paginated list response."""
    body = PaginatedEnvelope(
        data=items,
        pagination={
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "has_next": (page * page_size) < total,
            "has_prev": page > 1,
        },
    )
    return JSONResponse(content=body.model_dump())
