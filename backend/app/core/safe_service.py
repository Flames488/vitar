"""
Vitar v8 — Safe Service Execution Helpers

Replaces bare:
    result = something()

With:
    result = safe_call(something)

All service-layer functions should use these wrappers to prevent
silent failures from bubbling up as 500s without context.
"""

import logging
import functools
from typing import Any, Callable, Optional, TypeVar, Type
from fastapi import HTTPException

logger = logging.getLogger("vitar.safe_service")

T = TypeVar("T")


def safe_call(
    func: Callable,
    *args,
    default: Any = None,
    reraise: bool = False,
    context: str = "",
    **kwargs,
) -> Any:
    """
    Call func(*args, **kwargs) with full exception handling.

    - Logs the error with context
    - Returns `default` on failure (fail-open)
    - If reraise=True, raises HTTPException(500) instead

    Example:
        result = safe_call(payment_service.charge, amount=500, default=None, context="stripe charge")
    """
    try:
        return func(*args, **kwargs)
    except HTTPException:
        raise  # Always let FastAPI HTTP exceptions pass through
    except Exception as exc:
        label = context or getattr(func, "__name__", str(func))
        logger.error(
            f"Service call failed: {label}",
            exc_info=exc,
            extra={"service_call": label, "error": str(exc)},
        )
        if reraise:
            raise HTTPException(
                status_code=500,
                detail={"error": "Internal service error", "context": label},
            )
        return default


def safe_service(context: str = "", reraise: bool = True):
    """
    Decorator: wraps an entire service function with error handling.

    Usage:
        @safe_service("billing.charge_card")
        def charge_card(db, clinic_id, amount):
            return stripe.charge(...)

    With reraise=True (default), raises HTTPException(500) on failure.
    With reraise=False, returns None on failure (use for non-critical ops).
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            label = context or func.__qualname__
            try:
                return func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as exc:
                logger.error(
                    f"Service error in {label}",
                    exc_info=exc,
                    extra={"service": label, "error": str(exc)},
                )
                if reraise:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Internal error in {label}",
                    )
                return None
        return wrapper
    return decorator


def require_or_404(obj: Any, detail: str = "Resource not found") -> Any:
    """Raise 404 if obj is None/falsy. Returns obj otherwise."""
    if not obj:
        raise HTTPException(status_code=404, detail=detail)
    return obj


def require_or_409(condition: bool, detail: str) -> None:
    """Raise 409 Conflict if condition is True."""
    if condition:
        raise HTTPException(status_code=409, detail=detail)


def require_or_403(condition: bool, detail: str = "Forbidden") -> None:
    """Raise 403 if condition is False."""
    if not condition:
        raise HTTPException(status_code=403, detail=detail)
