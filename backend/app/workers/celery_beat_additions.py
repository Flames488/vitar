"""
Vitar — Celery Beat Schedule Additions

Add these entries to the `beat_schedule` dict in your celery_app.py.

Instructions:
  Open backend/app/workers/celery_app.py and find:
      app.conf.beat_schedule = { ... }
  Then add the two entries below.
"""

# ── Add these two entries to app.conf.beat_schedule ──────────────────────────
# (merge into your existing beat_schedule dict)

BEAT_SCHEDULE_ADDITIONS = {
    # Daily cleanup of expired/unsubscribed push endpoints.
    # Runs at 2 AM to keep push_subscriptions table lean.
    "cleanup-expired-push-subscriptions": {
        "task": "app.workers.push_tasks.cleanup_expired_push_subscriptions",
        "schedule": 86400,  # every 24 hours
        "options": {"queue": "celery"},
    },
}

# ── Also register the push_tasks module with Celery autodiscovery ─────────────
# In celery_app.py, update the include list:
#
#   app.conf.task_routes = {...}
#   app.autodiscover_tasks([
#       'app.workers.tasks',
#       'app.workers.push_tasks',   # ← add this line
#   ])
#
# OR just import it at the top of celery_app.py:
#   import app.workers.push_tasks  # noqa: F401
