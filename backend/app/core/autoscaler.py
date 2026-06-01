"""
Vitar v9 — Intelligent Autoscaler

Scales API replicas and Celery workers based on real-time signals:

  API scaling  → tracks request rate + p95 latency from Prometheus
  Worker scaling → tracks Celery queue depths from Redis LLEN

Architecture:
  - ScalingPolicy defines thresholds and limits per component
  - AutoScaler evaluates signals and emits scale-up / scale-down decisions
  - DockerScaler executes decisions via docker compose (default)
  - Can be swapped for KubernetesScaler / ECSScaler with same interface

Scaling is intentionally conservative:
  - Scale-up is fast  (triggered immediately on threshold breach)
  - Scale-down is slow (requires SCALE_DOWN_COOLDOWN_S stable window)
  - Min / max replica bounds prevent runaway scaling

Integration:
  Called from monitor_queue_depths Celery task (every 60 s)
  OR as a standalone cron: python -m app.core.autoscaler
"""

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

logger = logging.getLogger("vitar.autoscaler")

# ── Scaling policies ──────────────────────────────────────────────────────────

@dataclass
class ScalingPolicy:
    name: str
    min_replicas: int
    max_replicas: int

    # Scale-up triggers
    scale_up_threshold: float       # queue depth or RPS above this → +1
    scale_up_step: int = 1          # replicas to add per scale-up event

    # Scale-down triggers
    scale_down_threshold: float = 0  # metric below this for cooldown period → -1
    scale_down_step: int = 1         # replicas to remove per scale-down event
    scale_down_cooldown_s: float = 300  # must be below threshold this long

    # Tracking
    _below_threshold_since: Optional[float] = field(default=None, repr=False)


# Default policies — override via environment variables or Settings
WORKER_POLICY = ScalingPolicy(
    name="celery_worker",
    min_replicas=int(os.environ.get("WORKER_MIN_REPLICAS", "1")),
    max_replicas=int(os.environ.get("WORKER_MAX_REPLICAS", "8")),
    scale_up_threshold=float(os.environ.get("WORKER_SCALE_UP_QUEUE_DEPTH", "100")),
    scale_down_threshold=float(os.environ.get("WORKER_SCALE_DOWN_QUEUE_DEPTH", "20")),
    scale_down_cooldown_s=float(os.environ.get("WORKER_SCALE_DOWN_COOLDOWN_S", "300")),
)

API_POLICY = ScalingPolicy(
    name="api",
    min_replicas=int(os.environ.get("API_MIN_REPLICAS", "1")),
    max_replicas=int(os.environ.get("API_MAX_REPLICAS", "6")),
    scale_up_threshold=float(os.environ.get("API_SCALE_UP_RPS", "50")),      # req/s
    scale_down_threshold=float(os.environ.get("API_SCALE_DOWN_RPS", "10")),
    scale_down_cooldown_s=float(os.environ.get("API_SCALE_DOWN_COOLDOWN_S", "600")),
)


# ── Scale decision ─────────────────────────────────────────────────────────────

@dataclass
class ScaleDecision:
    component: str
    direction: Literal["up", "down", "none"]
    current_replicas: int
    target_replicas: int
    reason: str
    metric_value: float
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── Executor interface ────────────────────────────────────────────────────────

class BaseScaler:
    """Interface that all executor backends implement."""

    def get_replica_count(self, service: str) -> int:
        raise NotImplementedError

    def set_replica_count(self, service: str, count: int) -> bool:
        raise NotImplementedError


class DockerComposeScaler(BaseScaler):
    """
    Scales services via `docker compose scale`.
    Works in single-host Docker deployments.
    """

    def __init__(self, compose_dir: str = "/opt/vitar"):
        self.compose_dir = compose_dir
        self._compose_file = os.path.join(compose_dir, "docker-compose.yml")

    def get_replica_count(self, service: str) -> int:
        try:
            result = subprocess.run(
                ["docker", "compose", "-f", self._compose_file, "ps", "-q", service],
                capture_output=True, text=True, timeout=10,
                cwd=self.compose_dir,
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            return len(lines)
        except Exception as exc:
            logger.error(f"get_replica_count({service}) failed: {exc}")
            return 1  # assume at least 1 running

    def set_replica_count(self, service: str, count: int) -> bool:
        try:
            result = subprocess.run(
                [
                    "docker", "compose", "-f", self._compose_file,
                    "up", "-d", "--no-recreate",
                    "--scale", f"{service}={count}",
                    service,
                ],
                capture_output=True, text=True, timeout=60,
                cwd=self.compose_dir,
            )
            if result.returncode != 0:
                logger.error(
                    f"scale {service}={count} failed: {result.stderr}",
                    extra={"service": service, "target": count},
                )
                return False
            logger.info(
                f"Scaled {service} to {count} replicas",
                extra={"service": service, "replicas": count},
            )
            return True
        except Exception as exc:
            logger.error(f"set_replica_count({service}, {count}) failed: {exc}")
            return False


class DryRunScaler(BaseScaler):
    """Log-only scaler for testing autoscale logic without side effects."""

    def __init__(self):
        self._counts: dict[str, int] = {}

    def get_replica_count(self, service: str) -> int:
        return self._counts.get(service, 1)

    def set_replica_count(self, service: str, count: int) -> bool:
        self._counts[service] = count
        logger.info(f"[DRY RUN] Would scale {service} → {count} replicas")
        return True


# ── Core AutoScaler ───────────────────────────────────────────────────────────

class AutoScaler:
    """
    Evaluates scaling policies against real-time metrics and issues decisions.

    Usage (called from Celery task every 60 s):
        scaler = AutoScaler()
        decisions = scaler.evaluate_all()
    """

    def __init__(self, executor: Optional[BaseScaler] = None, dry_run: bool = False):
        if dry_run:
            self.executor = DryRunScaler()
        elif executor:
            self.executor = executor
        else:
            compose_dir = os.environ.get("COMPOSE_DIR", "/opt/vitar")
            self.executor = DockerComposeScaler(compose_dir=compose_dir)

    # ── Signal readers ────────────────────────────────────────────────────────

    def _get_total_queue_depth(self) -> float:
        """Sum of all non-DLQ queue depths from Redis."""
        try:
            import redis as redis_lib
            from app.core.config import settings
            r = redis_lib.from_url(
                settings.CELERY_BROKER_URL,
                decode_responses=True,
                socket_timeout=2,
            )
            queues = ["notifications", "reminders", "ai", "billing", "celery"]
            total = sum(r.llen(q) for q in queues)
            return float(total)
        except Exception as exc:
            logger.warning(f"Could not read queue depths: {exc}")
            return 0.0

    def _get_api_rps(self) -> float:
        """
        Read current request rate from Prometheus.
        Falls back to 0 if Prometheus is unavailable.
        """
        try:
            import httpx
            prom_url = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
            # rate over last 2 minutes
            query = 'sum(rate(vitar_http_requests_total[2m]))'
            resp = httpx.get(
                f"{prom_url}/api/v1/query",
                params={"query": query},
                timeout=3.0,
            )
            data = resp.json()
            results = data.get("data", {}).get("result", [])
            if results:
                return float(results[0]["value"][1])
            return 0.0
        except Exception as exc:
            logger.debug(f"Could not read Prometheus RPS: {exc}")
            return 0.0

    # ── Policy evaluation ─────────────────────────────────────────────────────

    def _evaluate_policy(
        self,
        policy: ScalingPolicy,
        service_name: str,
        metric_value: float,
    ) -> ScaleDecision:
        current = self.executor.get_replica_count(service_name)
        now = time.monotonic()

        # Scale UP check
        if metric_value >= policy.scale_up_threshold:
            target = min(current + policy.scale_up_step, policy.max_replicas)
            policy._below_threshold_since = None  # reset cooldown
            if target > current:
                return ScaleDecision(
                    component=service_name,
                    direction="up",
                    current_replicas=current,
                    target_replicas=target,
                    reason=f"metric {metric_value:.1f} ≥ threshold {policy.scale_up_threshold}",
                    metric_value=metric_value,
                )

        # Scale DOWN check — requires sustained low metric (cooldown)
        elif metric_value <= policy.scale_down_threshold and current > policy.min_replicas:
            if policy._below_threshold_since is None:
                policy._below_threshold_since = now
                logger.debug(
                    f"[{policy.name}] Scale-down cooldown started",
                    extra={"metric": metric_value, "threshold": policy.scale_down_threshold},
                )
            elif (now - policy._below_threshold_since) >= policy.scale_down_cooldown_s:
                target = max(current - policy.scale_down_step, policy.min_replicas)
                policy._below_threshold_since = None  # reset
                if target < current:
                    return ScaleDecision(
                        component=service_name,
                        direction="down",
                        current_replicas=current,
                        target_replicas=target,
                        reason=(
                            f"metric {metric_value:.1f} ≤ {policy.scale_down_threshold} "
                            f"for {policy.scale_down_cooldown_s:.0f}s"
                        ),
                        metric_value=metric_value,
                    )
        else:
            # Metric is between thresholds — reset the scale-down timer
            policy._below_threshold_since = None

        return ScaleDecision(
            component=service_name,
            direction="none",
            current_replicas=current,
            target_replicas=current,
            reason="within normal range",
            metric_value=metric_value,
        )

    # ── Execute decision ──────────────────────────────────────────────────────

    def _execute(self, decision: ScaleDecision) -> bool:
        if decision.direction == "none":
            return True

        logger.info(
            f"AUTOSCALE {decision.direction.upper()}: "
            f"{decision.component} {decision.current_replicas}→{decision.target_replicas} "
            f"({decision.reason})",
            extra={
                "component": decision.component,
                "direction": decision.direction,
                "from": decision.current_replicas,
                "to": decision.target_replicas,
                "metric": decision.metric_value,
            },
        )

        # Prometheus metric
        try:
            from app.core.metrics import AUTOSCALE_EVENTS
            AUTOSCALE_EVENTS.labels(
                direction=decision.direction,
                component=decision.component,
            ).inc()
        except Exception:
            pass

        # Slack alert on scale events
        try:
            from app.core.observability import send_alert, INFO
            send_alert(
                title=f"Autoscale {decision.direction}: {decision.component}",
                message=(
                    f"{decision.component} scaled {decision.direction}: "
                    f"{decision.current_replicas} → {decision.target_replicas} replicas. "
                    f"Reason: {decision.reason}"
                ),
                severity=INFO,
                component="autoscaler",
                extra={
                    "from_replicas": decision.current_replicas,
                    "to_replicas": decision.target_replicas,
                },
            )
        except Exception:
            pass

        return self.executor.set_replica_count(decision.component, decision.target_replicas)

    # ── Public API ────────────────────────────────────────────────────────────

    def evaluate_all(self) -> list[ScaleDecision]:
        """
        Evaluate all policies and execute any scaling decisions.
        Returns list of decisions (including "none" decisions for observability).
        """
        decisions = []

        # Worker autoscale (queue depth signal)
        queue_depth = self._get_total_queue_depth()
        worker_decision = self._evaluate_policy(WORKER_POLICY, "worker", queue_depth)
        self._execute(worker_decision)
        decisions.append(worker_decision)

        # Update worker gauge
        try:
            from app.core.metrics import WORKER_COUNT_GAUGE
            WORKER_COUNT_GAUGE.set(worker_decision.target_replicas)
        except Exception:
            pass

        # API autoscale (RPS signal from Prometheus)
        rps = self._get_api_rps()
        api_decision = self._evaluate_policy(API_POLICY, "api", rps)
        self._execute(api_decision)
        decisions.append(api_decision)

        # Update API gauge
        try:
            from app.core.metrics import API_REPLICA_GAUGE
            API_REPLICA_GAUGE.set(api_decision.target_replicas)
        except Exception:
            pass

        return decisions

    def status(self) -> dict:
        """Return current replica counts and metric snapshot."""
        return {
            "worker": {
                "replicas": self.executor.get_replica_count("worker"),
                "policy": {
                    "min": WORKER_POLICY.min_replicas,
                    "max": WORKER_POLICY.max_replicas,
                    "scale_up_threshold": WORKER_POLICY.scale_up_threshold,
                    "scale_down_threshold": WORKER_POLICY.scale_down_threshold,
                },
                "current_queue_depth": self._get_total_queue_depth(),
            },
            "api": {
                "replicas": self.executor.get_replica_count("api"),
                "policy": {
                    "min": API_POLICY.min_replicas,
                    "max": API_POLICY.max_replicas,
                    "scale_up_threshold_rps": API_POLICY.scale_up_threshold,
                    "scale_down_threshold_rps": API_POLICY.scale_down_threshold,
                },
                "current_rps": self._get_api_rps(),
            },
        }


# ── Celery task integration ───────────────────────────────────────────────────

def run_autoscaler():
    """
    Called from monitor_queue_depths Celery task (and optionally from cron).
    Dry-run mode if AUTOSCALE_DRY_RUN=true in environment.
    """
    dry_run = os.environ.get("AUTOSCALE_DRY_RUN", "false").lower() == "true"
    enabled = os.environ.get("AUTOSCALE_ENABLED", "false").lower() == "true"

    if not enabled:
        logger.debug("Autoscaler disabled (AUTOSCALE_ENABLED != true)")
        return []

    scaler = AutoScaler(dry_run=dry_run)
    try:
        decisions = scaler.evaluate_all()
        return [
            {
                "component": d.component,
                "direction": d.direction,
                "from": d.current_replicas,
                "to": d.target_replicas,
                "reason": d.reason,
            }
            for d in decisions
        ]
    except Exception as exc:
        logger.error(f"Autoscaler run failed: {exc}", exc_info=True)
        return []


# ── CLI entrypoint ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    scaler = AutoScaler(dry_run=True)
    decisions = scaler.evaluate_all()
    print(json.dumps([vars(d) for d in decisions], indent=2, default=str))
