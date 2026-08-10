"""
Vitar v9 — Celery Application (HARDENED)

Upgrades over v8:
  1. Queue-depth monitoring: Redis LLEN checked every minute, alerts if > threshold
  2. Dead-letter queue with automatic retry decay (task age gate)
  3. Per-queue concurrency limits to prevent AI/billing starvation
  4. Worker memory limit: --max-memory-per-child prevents OOM creep
  5. Prometheus metrics wired to all task outcomes (success/failure/retry)
  6. Worker heartbeat tracking in Redis (detected by watchdog)
  7. Beat schedule loaded from DB-backed config (future) — default schedule preserved
"""

from celery import Celery
from celery.schedules import crontab
from app.core.config import settings
from app.workers.celery_beat_additions import BEAT_SCHEDULE_ADDITIONS

celery = Celery(
    "vitar",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks", "app.workers.push_tasks", "app.agents.lead_hunter"],
)

beat_schedule = {
    "fire-pending-reminders": {
        "task": "app.workers.tasks.fire_pending_reminders",
        "schedule": 300.0,
    },
    "trial-nudges": {
        "task": "app.workers.tasks.send_trial_nudges",
        "schedule": crontab(hour=9, minute=0),
    },
    "expire-trials": {
        "task": "app.workers.tasks.expire_trial_subscriptions",
        "schedule": crontab(hour=0, minute=0),
    },
    "retry-failed-notifications": {
        "task": "app.workers.tasks.retry_failed_notifications",
        "schedule": 600.0,
    },
    "retry-failed-payments": {
        "task": "app.workers.tasks.retry_failed_payments",
        "schedule": 1800.0,
    },
    "refresh-risk-scores": {
        "task": "app.workers.tasks.refresh_upcoming_risk_scores",
        "schedule": crontab(minute=0),
    },
    "process-dead-letter": {
        "task": "app.workers.tasks.dead_letter_processor",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    "auto-send-pending-payouts": {
        "task": "app.workers.tasks.auto_send_pending_payouts",
        "schedule": crontab(minute=0),
    },
    "cleanup-expired-refresh-tokens": {
        "task": "app.workers.tasks.cleanup_expired_refresh_tokens",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "celery"},
    },
    "cancel-stale-awaiting-payment-appointments": {
        "task": "app.workers.tasks.cancel_stale_awaiting_payment_appointments",
        "schedule": 900.0,
    },
    # ── AI Core: Lead Hunter ────────────────────────────────────────────────
    "lead-hunter-daily": {
        "task": "app.agents.lead_hunter.hunt_leads_daily",
        "schedule": crontab(hour=6, minute=0),
        "options": {"queue": "ai"},
    },
}

# FIX: BEAT_SCHEDULE_ADDITIONS (cleanup-expired-push-subscriptions) was
# defined in celery_beat_additions.py but never merged in here — the task
# existed and its docstring claimed "runs daily", but it was never actually
# scheduled, so expired push subscriptions accumulated in the DB forever.
beat_schedule.update(BEAT_SCHEDULE_ADDITIONS)

if settings.OPS_MONITORING_ENABLED:
    beat_schedule.update({
        "monitor-queue-depths": {
            "task": "app.workers.tasks.monitor_queue_depths",
            "schedule": 60.0,
        },
        "monitor-system-resources": {
            "task": "app.workers.tasks.monitor_system_resources",
            "schedule": 60.0,
        },
        "inspect-stuck-tasks": {
            "task": "app.workers.tasks.inspect_stuck_tasks",
            "schedule": 300.0,
        },
    })


celery.conf.update(
    # ── Serialization ──────────────────────────────────────────────────────
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # ── Reliability ────────────────────────────────────────────────────────
    # ACK only AFTER task completes — re-queued if worker dies mid-task
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # ── Time limits ────────────────────────────────────────────────────────
    task_soft_time_limit=120,    # 2 min: SoftTimeLimitExceeded for graceful cleanup
    task_time_limit=180,         # 3 min: hard SIGKILL

    # ── Result expiry ──────────────────────────────────────────────────────
    result_expires=86400,        # 24 hours

    # ── Concurrency / prefetch ─────────────────────────────────────────────
    # worker_prefetch_multiplier=1 prevents one worker from hoarding tasks.
    # Combined with --max-memory-per-child in Dockerfile.worker to prevent OOM.
    worker_prefetch_multiplier=1,
    task_always_eager=False,

    # ── Beat schedule persistence ──────────────────────────────────────────
    beat_schedule_filename="/var/celery/celerybeat-schedule",

    # ── Compression: reduce Redis memory for large task payloads ──────────
    task_compression="gzip",
    result_compression="gzip",

    # ── Routing ────────────────────────────────────────────────────────────
    task_routes={
        "app.workers.tasks.send_notification_job":          {"queue": "notifications"},
        "app.workers.tasks.calculate_no_show_risk":         {"queue": "ai"},
        "app.workers.tasks.schedule_appointment_reminders": {"queue": "reminders"},
        "app.workers.tasks.fire_pending_reminders":         {"queue": "reminders"},
        "app.workers.tasks.notify_waiting_list":            {"queue": "notifications"},
        "app.workers.tasks.handle_no_show_followup":        {"queue": "notifications"},
        "app.workers.tasks.send_trial_nudges":              {"queue": "billing"},
        "app.workers.tasks.expire_trial_subscriptions":     {"queue": "billing"},
        "app.workers.tasks.retry_failed_notifications":     {"queue": "notifications"},
        "app.workers.tasks.retry_failed_payments":          {"queue": "billing"},
        "app.workers.tasks.auto_send_pending_payouts":      {"queue": "billing"},
        "app.workers.tasks.refresh_upcoming_risk_scores":   {"queue": "ai"},
        "app.workers.tasks.dead_letter_processor":          {"queue": "dead_letter"},
        "app.workers.tasks.update_patient_attendance":      {"queue": "notifications"},
        "app.workers.tasks.send_reschedule_notification":   {"queue": "notifications"},
        # v9: queue depth monitor
        "app.workers.tasks.monitor_queue_depths":           {"queue": "celery"},
        # v10: system + stuck-task monitors
        "app.workers.tasks.monitor_system_resources":       {"queue": "celery"},
        "app.workers.tasks.inspect_stuck_tasks":            {"queue": "celery"},
        "app.workers.tasks.cleanup_expired_refresh_tokens": {"queue": "celery"},
    },

    # ── Beat schedule ──────────────────────────────────────────────────────
    beat_schedule=beat_schedule,
)


# ── Prometheus metrics signals ────────────────────────────────────────────────
try:
    from celery.signals import task_success, task_failure, task_retry
    from app.core.metrics import record_celery_task

    @task_success.connect
    def on_task_success(sender=None, **kwargs):
        task_name = getattr(sender, "name", str(sender)) if sender else "unknown"
        record_celery_task(task_name, "success")

    @task_failure.connect
    def on_task_failure_metric(sender=None, exception=None, **kwargs):
        task_name = getattr(sender, "name", str(sender)) if sender else "unknown"
        record_celery_task(task_name, "failure")

    @task_retry.connect
    def on_task_retry(sender=None, **kwargs):
        task_name = getattr(sender, "name", str(sender)) if sender else "unknown"
        record_celery_task(task_name, "retry")

except ImportError:
    pass


# ── Worker heartbeat ──────────────────────────────────────────────────────────
try:
    from celery.signals import worker_ready

    @worker_ready.connect
    def on_worker_ready(sender=None, **kwargs):
        try:
            from app.core.observability import worker_heartbeat
            import os
            worker_id = os.environ.get("CELERY_WORKER_HOSTNAME", f"worker@{os.uname().nodename}")
            worker_heartbeat(worker_id, interval_seconds=30)
        except Exception as exc:
            import logging
            logging.getLogger("vitar.celery").warning(f"Heartbeat init failed: {exc}")

except ImportError:
    pass
