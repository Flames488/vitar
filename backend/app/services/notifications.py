"""
Vitar AI Core — Shared Notification Service

The single place any AI Core agent creates a notification. Every agent
(Lead Hunter, Sales Agent, Content Agent, Customer Success) calls notify()
instead of pushing to Telegram or anywhere else directly — this is the only
place a row is ever inserted into agent_notifications, so the superadmin
dashboard's notification center and the Telegram bot (both independent
readers of that same table) can never drift out of sync or miss an event
the other caught.

notify() opens and closes its own short-lived session rather than taking
one from the caller: agents call this from many different contexts (Celery
tasks with their own SessionLocal session open for other work, admin API
endpoints with a request-scoped session), and a notification is a
side-effect that shouldn't be tangled up in the caller's own transaction —
if the caller's transaction later rolls back, the notification (which
usually reports "this already happened") should still stand.
"""
import logging
from typing import Optional

from app.core.database import SessionLocal
from app.models.models import AgentNotification, NotificationEventType

logger = logging.getLogger("vitar.ai_core.notifications")


def notify(
    event_type: str,
    agent_name: str,
    message: str,
    related_id: Optional[str] = None,
    link_path: Optional[str] = None,
) -> None:
    """
    Insert one row into agent_notifications. Never raises — a notification
    failure must never take down the agent run that triggered it.

    event_type must be one of NotificationEventType's values (e.g.
    "leads_found", "outreach_ready", "lead_replied", "lead_trial_started",
    "content_ready", "health_signal", "agent_failed").
    """
    try:
        NotificationEventType(event_type)  # validates against the real enum
    except ValueError:
        logger.error(
            "notify() called with unknown event_type=%r — skipping insert",
            event_type,
        )
        return

    db = SessionLocal()
    try:
        db.add(AgentNotification(
            event_type=event_type,
            agent_name=agent_name,
            message=message,
            related_id=related_id,
            link_path=link_path,
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.error(
            "notify() failed to write notification | agent=%s event=%s",
            agent_name, event_type, exc_info=True,
        )
    finally:
        db.close()
