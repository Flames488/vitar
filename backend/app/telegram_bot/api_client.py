"""
Vitar AI Core — Telegram Bot: shared internal API client.

Extracted out of bot.py so the free-text assistant (assistant.py) can call
the same authenticated admin endpoints without bot.py importing assistant.py
and assistant.py importing bot.py back (circular import).
"""
import asyncio
from datetime import timedelta

import httpx

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import create_access_token

# Internal docker-network address of the api service (see docker-compose.yml)
# — not the public livevault.cloud/nginx path. Keeps ops-bot traffic off the
# public edge entirely.
API_BASE = "http://api:8000/api/v1"

_superadmin_user_id_cache: str | None = None


def _get_superadmin_user_id() -> str:
    """Looked up once and cached — used only to mint short-lived JWTs so the
    bot can call the real admin endpoints, never used for anything else."""
    global _superadmin_user_id_cache
    if _superadmin_user_id_cache:
        return _superadmin_user_id_cache
    from app.models.models import User

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.is_superadmin == True, User.is_active == True)  # noqa: E712
            .first()
        )
        if not user:
            raise RuntimeError("No active superadmin user found — the Telegram bot needs one to mint API tokens")
        _superadmin_user_id_cache = user.id
        return user.id
    finally:
        db.close()


async def call_api(method: str, path: str, **kwargs) -> dict:
    user_id = await asyncio.to_thread(_get_superadmin_user_id)
    token = create_access_token({"sub": user_id}, expires_delta=timedelta(minutes=5))
    async with httpx.AsyncClient(base_url=API_BASE, timeout=20) as client:
        resp = await client.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        resp.raise_for_status()
        return resp.json()
