"""
Vitar AI Core — Shared AI Provider Layer

Every AI Core agent (Lead Hunter, Sales Agent, Content Agent, Customer
Success) calls generate() instead of instantiating its own Groq client —
this is the only place model/retry/usage-logging behavior lives, so
tuning it (model swap, retry policy, rate limiting) happens once for every
agent instead of N times.

Uses the sync Groq client, not the AsyncGroq client app/api/v1/endpoints/
ai.py's chatbot endpoint uses — that endpoint is an async FastAPI route;
AI Core agents are plain sync Celery tasks (see app/workers/tasks.py for
the established pattern), so a sync client fits the actual call site
instead of requiring every agent task to spin up its own event loop just
to call this.
"""
import logging
import time
from typing import Optional

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import AiUsageLog

logger = logging.getLogger("vitar.ai_core.ai_provider")

DEFAULT_MODEL = "llama-3.3-70b-versatile"
_MAX_RETRIES = 2
_RETRY_BASE_DELAY_S = 1.5


def generate(
    prompt: str,
    agent_name: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Calls Groq and returns the completion text. Retries up to _MAX_RETRIES
    times with exponential backoff on failure, then raises the last error —
    callers (agent tasks) decide how to handle a persistent failure (skip
    this item, let Celery's own retry take over, etc.), this layer only
    handles transient provider blips.

    agent_name is required (not optional, despite not being part of the
    original 4-arg generate(prompt, system, model) signature) because
    every call is logged to ai_usage_log for per-agent AI spend tracking —
    that table is meaningless without knowing which agent made the call.
    """
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not configured — cannot call generate()")

    from groq import Groq

    client = Groq(api_key=settings.GROQ_API_KEY)
    use_model = model or DEFAULT_MODEL
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            completion = client.chat.completions.create(
                model=use_model,
                messages=messages,
            )
            text = completion.choices[0].message.content or ""
            tokens = getattr(completion.usage, "total_tokens", 0) if completion.usage else 0
            _log_usage(agent_name, tokens, use_model)
            return text
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY_S * (2 ** attempt)
                logger.warning(
                    "ai_provider.generate() attempt %d/%d failed | agent=%s error=%s — retrying in %.1fs",
                    attempt + 1, _MAX_RETRIES + 1, agent_name, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "ai_provider.generate() exhausted retries | agent=%s error=%s",
                    agent_name, exc, exc_info=True,
                )

    raise last_exc  # type: ignore[misc]


def _log_usage(agent_name: str, tokens_used: int, model: str) -> None:
    """Best-effort — a logging failure must never break the actual generate() call."""
    db = SessionLocal()
    try:
        db.add(AiUsageLog(agent_name=agent_name, tokens_used=tokens_used, model=model))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to log AI usage | agent=%s", agent_name, exc_info=True)
    finally:
        db.close()
