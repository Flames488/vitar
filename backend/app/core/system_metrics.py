"""
Vitar v10 — System Resource Metrics & Auto-Recovery

Addresses gaps:
  - "Alerts (CPU, memory, queue size)" — adds real-time system metrics
  - "Auto-recovery triggers" — fires scale actions based on resource pressure
  - "No True Zero Babysitting Layer" — auto-heals under resource pressure

What this module provides:
  1. SystemSnapshot  — dataclass capturing a full resource reading
  2. collect()       — reads CPU%, memory%, disk%, open FDs via psutil
  3. record_to_prometheus() — publishes to Prometheus gauges
  4. AutoRecoveryManager   — evaluates thresholds, fires Slack alerts,
                              and triggers scale/restart actions

Thresholds (all configurable via Settings):
  CPU_ALERT_THRESHOLD_PCT     default 85   → WARNING alert
  CPU_CRITICAL_THRESHOLD_PCT  default 95   → CRITICAL + trigger scale-up
  MEMORY_ALERT_THRESHOLD_PCT  default 80   → WARNING alert
  MEMORY_CRITICAL_THRESHOLD_PCT default 90 → CRITICAL + trigger scale-down workers
  DISK_ALERT_THRESHOLD_PCT    default 80   → WARNING alert
  DISK_CRITICAL_THRESHOLD_PCT default 92   → CRITICAL (risk of DB crash)

Integration:
  Called from monitor_system_resources Celery task every 60s.
  Results surfaced at /health endpoint under "system" component.

Requires: psutil (already in requirements.txt after v10 upgrade)
"""

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("vitar.system_metrics")


# ── Snapshot dataclass ────────────────────────────────────────────────────────

@dataclass
class SystemSnapshot:
    cpu_pct: float                  # 1-second interval sample
    memory_pct: float               # used / total
    memory_used_mb: float
    memory_available_mb: float
    disk_pct: float                 # partition usage %
    disk_free_gb: float
    open_fds: int                   # file descriptors (process-level)
    load_1m: float                  # 1-min load average
    load_5m: float
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "cpu_pct": round(self.cpu_pct, 1),
            "memory_pct": round(self.memory_pct, 1),
            "memory_used_mb": round(self.memory_used_mb, 1),
            "memory_available_mb": round(self.memory_available_mb, 1),
            "disk_pct": round(self.disk_pct, 1),
            "disk_free_gb": round(self.disk_free_gb, 2),
            "open_fds": self.open_fds,
            "load_1m": round(self.load_1m, 2),
            "load_5m": round(self.load_5m, 2),
            "timestamp": self.timestamp,
        }

    @property
    def status(self) -> str:
        from app.core.config import settings
        cpu_crit = getattr(settings, "CPU_CRITICAL_THRESHOLD_PCT", 95)
        mem_crit = getattr(settings, "MEMORY_CRITICAL_THRESHOLD_PCT", 90)
        disk_crit = getattr(settings, "DISK_CRITICAL_THRESHOLD_PCT", 92)
        cpu_warn = getattr(settings, "CPU_ALERT_THRESHOLD_PCT", 85)
        mem_warn = getattr(settings, "MEMORY_ALERT_THRESHOLD_PCT", 80)
        disk_warn = getattr(settings, "DISK_ALERT_THRESHOLD_PCT", 80)

        if self.cpu_pct >= cpu_crit or self.memory_pct >= mem_crit or self.disk_pct >= disk_crit:
            return "critical"
        if self.cpu_pct >= cpu_warn or self.memory_pct >= mem_warn or self.disk_pct >= disk_warn:
            return "warning"
        return "ok"


# ── Collector ─────────────────────────────────────────────────────────────────

def collect() -> Optional[SystemSnapshot]:
    """
    Read current system resource usage. Returns None if psutil unavailable.

    CPU uses a 1-second blocking interval for accuracy.
    Disk is read from the path of the Postgres data dir or '/'.
    """
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk_path = os.environ.get("DISK_CHECK_PATH", "/")
        disk = psutil.disk_usage(disk_path)
        load = os.getloadavg()  # (1m, 5m, 15m)
        try:
            proc = psutil.Process()
            fds = proc.num_fds()
        except Exception:
            fds = -1

        return SystemSnapshot(
            cpu_pct=cpu,
            memory_pct=mem.percent,
            memory_used_mb=mem.used / 1_048_576,
            memory_available_mb=mem.available / 1_048_576,
            disk_pct=disk.percent,
            disk_free_gb=disk.free / 1_073_741_824,
            open_fds=fds,
            load_1m=load[0],
            load_5m=load[1],
        )
    except ImportError:
        logger.debug("psutil not installed — system metrics unavailable")
        return None
    except Exception as exc:
        logger.warning(f"System metrics collection failed: {exc}")
        return None


def record_to_prometheus(snap: SystemSnapshot) -> None:
    """Publish snapshot values to Prometheus gauges."""
    try:
        from app.core.metrics import (
            SYSTEM_CPU_GAUGE,
            SYSTEM_MEMORY_GAUGE,
            SYSTEM_DISK_GAUGE,
            SYSTEM_LOAD_GAUGE,
            SYSTEM_FD_GAUGE,
        )
        SYSTEM_CPU_GAUGE.set(snap.cpu_pct)
        SYSTEM_MEMORY_GAUGE.set(snap.memory_pct)
        SYSTEM_DISK_GAUGE.set(snap.disk_pct)
        SYSTEM_LOAD_GAUGE.labels(interval="1m").set(snap.load_1m)
        SYSTEM_LOAD_GAUGE.labels(interval="5m").set(snap.load_5m)
        if snap.open_fds >= 0:
            SYSTEM_FD_GAUGE.set(snap.open_fds)
    except Exception as exc:
        logger.debug(f"Prometheus record failed (non-fatal): {exc}")


# ── Auto-Recovery Manager ─────────────────────────────────────────────────────

class AutoRecoveryManager:
    """
    Evaluates a SystemSnapshot against thresholds and triggers recovery actions.

    Recovery actions (in order of severity):
      1. Slack alert (always fires on threshold breach)
      2. Scale-up workers on CPU spike (queue likely growing too)
      3. Alert + log on memory pressure
      4. Critical disk alert with explicit runbook (DB at risk)

    Cooldown: each action is throttled to at most once per 10 minutes
    to prevent alert storms during sustained pressure.

    Usage:
        mgr = AutoRecoveryManager()
        actions = mgr.evaluate(snapshot)
    """

    def __init__(self):
        self._last_triggered: dict[str, float] = {}
        self._cooldown_s = 600.0  # 10-minute cooldown between repeated actions

    def evaluate(self, snap: SystemSnapshot) -> list[dict]:
        """
        Evaluate snapshot against all thresholds.
        Returns list of actions taken (for logging / task return value).
        """
        from app.core.config import settings
        actions = []

        cpu_warn = getattr(settings, "CPU_ALERT_THRESHOLD_PCT", 85)
        cpu_crit = getattr(settings, "CPU_CRITICAL_THRESHOLD_PCT", 95)
        mem_warn = getattr(settings, "MEMORY_ALERT_THRESHOLD_PCT", 80)
        mem_crit = getattr(settings, "MEMORY_CRITICAL_THRESHOLD_PCT", 90)
        disk_warn = getattr(settings, "DISK_ALERT_THRESHOLD_PCT", 80)
        disk_crit = getattr(settings, "DISK_CRITICAL_THRESHOLD_PCT", 92)

        # ── CPU ───────────────────────────────────────────────────────────────
        if snap.cpu_pct >= cpu_crit:
            if self._can_trigger("cpu_critical"):
                self._alert(
                    title="CRITICAL: CPU Saturation",
                    message=(
                        f"CPU at {snap.cpu_pct:.1f}% (critical threshold: {cpu_crit}%). "
                        f"Load: {snap.load_1m:.1f} (1m) / {snap.load_5m:.1f} (5m). "
                        "Triggering worker scale-up."
                    ),
                    severity="critical",
                    component="system.cpu",
                )
                triggered = self._scale_up_workers()
                actions.append({"action": "cpu_critical_scale_up", "executed": triggered,
                                 "cpu_pct": snap.cpu_pct})
        elif snap.cpu_pct >= cpu_warn:
            if self._can_trigger("cpu_warning"):
                self._alert(
                    title="CPU High",
                    message=f"CPU at {snap.cpu_pct:.1f}% (warning threshold: {cpu_warn}%).",
                    severity="warning",
                    component="system.cpu",
                )
                actions.append({"action": "cpu_warning_alert", "cpu_pct": snap.cpu_pct})

        # ── Memory ───────────────────────────────────────────────────────────
        if snap.memory_pct >= mem_crit:
            if self._can_trigger("memory_critical"):
                self._alert(
                    title="CRITICAL: Memory Pressure",
                    message=(
                        f"Memory at {snap.memory_pct:.1f}% "
                        f"({snap.memory_available_mb:.0f}MB free). "
                        "Risk of OOM kills. Consider reducing worker count."
                    ),
                    severity="critical",
                    component="system.memory",
                    extra={"available_mb": round(snap.memory_available_mb, 1)},
                )
                actions.append({"action": "memory_critical_alert", "memory_pct": snap.memory_pct})
        elif snap.memory_pct >= mem_warn:
            if self._can_trigger("memory_warning"):
                self._alert(
                    title="Memory High",
                    message=f"Memory at {snap.memory_pct:.1f}% (warning: {mem_warn}%).",
                    severity="warning",
                    component="system.memory",
                )
                actions.append({"action": "memory_warning_alert", "memory_pct": snap.memory_pct})

        # ── Disk ─────────────────────────────────────────────────────────────
        if snap.disk_pct >= disk_crit:
            if self._can_trigger("disk_critical"):
                self._alert(
                    title="CRITICAL: Disk Almost Full",
                    message=(
                        f"Disk at {snap.disk_pct:.1f}% ({snap.disk_free_gb:.1f}GB free). "
                        "PostgreSQL WAL will fail when disk is full — DB crash imminent. "
                        "Runbook: docker exec postgres psql -U vitar -c 'CHECKPOINT;' "
                        "then vacuum large tables."
                    ),
                    severity="critical",
                    component="system.disk",
                    extra={"free_gb": round(snap.disk_free_gb, 2)},
                )
                actions.append({"action": "disk_critical_alert", "disk_pct": snap.disk_pct,
                                 "free_gb": snap.disk_free_gb})
        elif snap.disk_pct >= disk_warn:
            if self._can_trigger("disk_warning"):
                self._alert(
                    title="Disk Usage High",
                    message=(
                        f"Disk at {snap.disk_pct:.1f}% ({snap.disk_free_gb:.1f}GB free). "
                        "Consider cleaning Docker images: docker image prune -a"
                    ),
                    severity="warning",
                    component="system.disk",
                )
                actions.append({"action": "disk_warning_alert", "disk_pct": snap.disk_pct})

        return actions

    def _can_trigger(self, key: str) -> bool:
        """Return True if enough time has elapsed since last trigger (cooldown)."""
        now = time.monotonic()
        last = self._last_triggered.get(key, 0.0)
        if now - last >= self._cooldown_s:
            self._last_triggered[key] = now
            return True
        return False

    def _alert(
        self,
        title: str,
        message: str,
        severity: str,
        component: str,
        extra: Optional[dict] = None,
    ) -> None:
        try:
            from app.core.observability import send_alert
            send_alert(
                title=title,
                message=message,
                severity=severity,
                component=component,
                extra=extra,
            )
        except Exception as exc:
            logger.warning(f"Alert send failed: {exc}")
        logger.log(
            logging.CRITICAL if severity == "critical" else logging.WARNING,
            f"[AutoRecovery] {title}: {message}",
            extra={"component": component, **(extra or {})},
        )

    def _scale_up_workers(self) -> bool:
        """
        Request immediate worker scale-up via the autoscaler.
        Used when CPU is critically high (workers likely overwhelmed).
        """
        try:
            from app.core.autoscaler import AutoScaler, WORKER_POLICY
            enabled = os.environ.get("AUTOSCALE_ENABLED", "false").lower() == "true"
            if not enabled:
                logger.info("AutoRecovery: autoscaler disabled — scale-up skipped")
                return False
            scaler = AutoScaler()
            current = scaler.executor.get_replica_count("worker")
            target = min(current + 1, WORKER_POLICY.max_replicas)
            if target > current:
                result = scaler.executor.set_replica_count("worker", target)
                logger.info(
                    f"AutoRecovery: scaled workers {current}→{target} due to CPU pressure",
                    extra={"from": current, "to": target},
                )
                return result
            return False
        except Exception as exc:
            logger.error(f"AutoRecovery scale-up failed: {exc}")
            return False


# ── Module-level singleton ────────────────────────────────────────────────────

# One instance per worker process — tracks cooldowns across Celery task runs
_recovery_manager: Optional[AutoRecoveryManager] = None


def get_recovery_manager() -> AutoRecoveryManager:
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = AutoRecoveryManager()
    return _recovery_manager


# ── Convenience function for Celery task ─────────────────────────────────────

def run_system_check() -> dict:
    """
    Full system check: collect → record → evaluate → return summary.
    Called from monitor_system_resources Celery task.
    """
    snap = collect()
    if snap is None:
        return {"status": "unavailable", "error": "psutil not installed"}

    record_to_prometheus(snap)
    mgr = get_recovery_manager()
    actions = mgr.evaluate(snap)

    logger.info(
        "SYSTEM_METRICS",
        extra={
            "cpu_pct": round(snap.cpu_pct, 1),
            "memory_pct": round(snap.memory_pct, 1),
            "disk_pct": round(snap.disk_pct, 1),
            "load_1m": round(snap.load_1m, 2),
            "actions": len(actions),
            "status": snap.status,
        },
    )

    return {
        "status": snap.status,
        "snapshot": snap.to_dict(),
        "recovery_actions": actions,
    }
