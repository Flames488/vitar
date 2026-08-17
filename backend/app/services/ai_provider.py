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


def _chat(
    messages: list,
    agent_name: str,
    model: Optional[str] = None,
    tools: Optional[list] = None,
    tool_choice: Optional[str] = None,
):
    """
    Shared call+retry+usage-logging core behind generate() and chat_with_tools().
    Retries up to _MAX_RETRIES times with exponential backoff on failure, then
    raises the last error — callers decide how to handle a persistent failure.
    Returns the raw completion.choices[0].message (caller picks .content /
    .tool_calls off it as needed).
    """
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not configured — cannot call the AI provider")

    from groq import Groq

    client = Groq(api_key=settings.GROQ_API_KEY)
    use_model = model or DEFAULT_MODEL
    kwargs = {}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            completion = client.chat.completions.create(
                model=use_model,
                messages=messages,
                **kwargs,
            )
            message = completion.choices[0].message
            tokens = getattr(completion.usage, "total_tokens", 0) if completion.usage else 0
            _log_usage(agent_name, tokens, use_model)
            return message
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY_S * (2 ** attempt)
                logger.warning(
                    "ai_provider._chat() attempt %d/%d failed | agent=%s error=%s — retrying in %.1fs",
                    attempt + 1, _MAX_RETRIES + 1, agent_name, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "ai_provider._chat() exhausted retries | agent=%s error=%s",
                    agent_name, exc, exc_info=True,
                )

    raise last_exc  # type: ignore[misc]


def generate(
    prompt: str,
    agent_name: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Calls Groq and returns the completion text.

    agent_name is required (not optional, despite not being part of the
    original 4-arg generate(prompt, system, model) signature) because
    every call is logged to ai_usage_log for per-agent AI spend tracking —
    that table is meaningless without knowing which agent made the call.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    message = _chat(messages, agent_name, model=model)
    return message.content or ""


def chat_with_tools(
    messages: list,
    agent_name: str,
    tools: list,
    model: Optional[str] = None,
):
    """
    Like generate(), but for multi-turn tool-calling conversations: the
    caller passes the full running message list (system/user/assistant/tool
    roles) and gets back the raw assistant message, which may carry
    `.tool_calls` instead of (or alongside) `.content` for the caller to
    execute and feed back in a follow-up call.
    """
    return _chat(messages, agent_name, model=model, tools=tools, tool_choice="auto")


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
