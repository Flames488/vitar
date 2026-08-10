"""
Vitar AI Core — Agent Task Utilities

log_agent_run: wraps a Celery agent task body, writing one AgentRun row
per execution (start/end time, status, item counts, error message) so the
superadmin dashboard's agent status dots and run history can be built
purely from this table.

is_dry_run: the single place that reads the DRY_RUN setting. Agent code
should call this rather than reading settings.DRY_RUN directly, so the
"what counts as dry-run mode" decision lives in one place.
"""
import functools
import inspect
import logging
from datetime import datetime
from typing import Optional

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.utils import utcnow
from app.models.models import AgentRun, AgentRunStatus

logger = logging.getLogger("vitar.ai_core.agent_runs")


def is_dry_run() -> bool:
    return settings.DRY_RUN


class AgentRunHandle:
    """
    Mutable state a wrapped task body reports progress through — set
    run.items_processed / run.items_created before the `with` block (or
    the decorated function) exits. run.partial = True marks the run
    status='partial' instead of 'success' even though nothing raised
    (e.g. some items succeeded, some were skipped for a known reason).
    """
    def __init__(self):
        self.items_processed = 0
        self.items_created = 0
        self.partial = False


class log_agent_run:
    """
    Usable as a context manager (preferred — lets the task body report
    counts directly):

        def hunt_leads(city):
            with log_agent_run("lead_hunter", "hunt_leads") as run:
                leads = scrape(city)
                run.items_processed = len(leads)
                run.items_created = upsert(leads)

    Or as a decorator, for tasks that don't need to report custom counts.
    If the wrapped function declares a `run` parameter, it receives the
    AgentRunHandle so it can still report counts; otherwise counts stay 0:

        @log_agent_run("content_agent", "draft_weekly_content")
        def draft_weekly_content(run=None):
            drafts = generate_drafts()
            if run:
                run.items_created = len(drafts)

    Either way: an uncaught exception is recorded as status='failed' with
    error_message set, then re-raised unchanged — this utility observes
    and logs, it never swallows an error or blocks Celery's own retry
    handling.

    Concurrency note: as a decorator, each call to the wrapped function
    constructs a fresh log_agent_run instance for its own `with` block
    (see __call__) rather than reusing the instance created at decoration
    time — that instance is shared across every call (and, under Celery,
    potentially concurrent calls), so its own _run/_started_at must never
    be treated as per-call state.
    """

    def __init__(self, agent_name: str, task_name: str):
        self.agent_name = agent_name
        self.task_name = task_name
        self._run: Optional[AgentRunHandle] = None
        self._started_at: Optional[datetime] = None

    def __enter__(self) -> AgentRunHandle:
        self._started_at = utcnow()
        self._run = AgentRunHandle()
        return self._run

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        finished_at = utcnow()
        run = self._run or AgentRunHandle()

        if exc_type is not None:
            status = AgentRunStatus.FAILED
            error_message = f"{exc_type.__name__}: {exc_val}"
        elif run.partial:
            status = AgentRunStatus.PARTIAL
            error_message = None
        else:
            status = AgentRunStatus.SUCCESS
            error_message = None

        self._write(status, finished_at, run, error_message)
        return False  # never swallow the exception

    def __call__(self, func):
        agent_name, task_name = self.agent_name, self.task_name
        wants_run = "run" in inspect.signature(func).parameters

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with log_agent_run(agent_name, task_name) as run:  # fresh instance per call
                if wants_run:
                    kwargs["run"] = run
                return func(*args, **kwargs)
        return wrapper

    def _write(self, status, finished_at, run: AgentRunHandle, error_message: Optional[str]):
        db = SessionLocal()
        try:
            db.add(AgentRun(
                agent_name=self.agent_name,
                task_name=self.task_name,
                status=status,
                started_at=self._started_at,
                finished_at=finished_at,
                items_processed=run.items_processed,
                items_created=run.items_created,
                error_message=error_message,
            ))
            db.commit()
        except Exception:
            db.rollback()
            logger.error(
                "Failed to write agent_runs row | agent=%s task=%s",
                self.agent_name, self.task_name, exc_info=True,
            )
        finally:
            db.close()
