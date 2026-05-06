#!/usr/bin/env python3
"""
Observability helpers: structured logging, Prometheus metrics, and lightweight
security/anomaly tracking for the personal AI agent.
"""
import json
import logging
import os
import re
import time
from typing import Dict, Optional

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    start_http_server,
)


# Prometheus metrics
REQUEST_COUNTER = Counter(
    "agent_requests_total",
    "Total agent requests by status and entrypoint.",
    ["status", "source"],
)
REQUEST_LATENCY = Histogram(
    "agent_request_latency_seconds",
    "Latency for agent responses.",
    ["source"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
SECURITY_EVENTS = Counter(
    "agent_security_events_total",
    "Security, compliance, or anomaly events.",
    ["event_type"],
)
SESSION_HEALTH = Gauge(
    "agent_session_status",
    "1 when the agent loop/API is running; 0 when stopped.",
)

# Additional metrics for alert rules
UPTIME_GAUGE = Gauge(
    "agent_uptime_seconds",
    "Seconds since the agent was started.",
)
ACTIVE_SESSIONS = Gauge(
    "agent_active_sessions",
    "Number of active agent sessions.",
)
COMPLIANCE_VIOLATIONS = Counter(
    "agent_compliance_violations_total",
    "Total compliance violations detected.",
)

# Track start time for uptime calculation
_start_time = time.time()


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: Dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            payload.update(record.extra)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> None:
    """Configure root and audit loggers with JSON output."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    audit_log_path = os.getenv("AUDIT_LOG_PATH")

    formatter = JsonFormatter()
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)
    root.addHandler(stream_handler)

    audit_logger = logging.getLogger("audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = True
    if audit_log_path:
        audit_log_dir = os.path.dirname(audit_log_path)
        try:
            if audit_log_dir:
                os.makedirs(audit_log_dir, exist_ok=True)
            file_handler = logging.FileHandler(audit_log_path)
            file_handler.setFormatter(formatter)
            audit_logger.addHandler(file_handler)
        except OSError as exc:
            root.warning(
                "Failed to initialize audit file logging; continuing with stdout-only logging.",
                extra={"extra": {"audit_log_path": audit_log_path, "error": str(exc)}},
            )


def start_metrics_server(host: Optional[str] = None, port: Optional[int] = None) -> None:
    """
    Launch a Prometheus metrics HTTP server (CLI mode).
    FastAPI mode uses the /metrics endpoint instead.
    """
    if host is None:
        host = os.getenv("METRICS_HOST", "0.0.0.0")
    if port is None:
        port = int(os.getenv("METRICS_PORT", "9000"))
    # start_http_server is idempotent enough for single-process usage.
    start_http_server(port, addr=host)


def set_session_status(running: bool) -> None:
    """Set the session status and update uptime"""
    SESSION_HEALTH.set(1 if running else 0)
    if running:
        ACTIVE_SESSIONS.inc()
        update_uptime()
    else:
        ACTIVE_SESSIONS.dec()


def update_uptime() -> None:
    """Update the uptime gauge"""
    uptime = time.time() - _start_time
    UPTIME_GAUGE.set(uptime)


def record_request_outcome(status: str, duration_seconds: float, source: str) -> None:
    REQUEST_COUNTER.labels(status=status, source=source).inc()
    REQUEST_LATENCY.labels(source=source).observe(duration_seconds)
    update_uptime()


def record_security_event(event_type: str) -> None:
    SECURITY_EVENTS.labels(event_type=event_type).inc()


def record_compliance_violation() -> None:
    """Record a compliance violation"""
    COMPLIANCE_VIOLATIONS.inc()


SUSPICIOUS_PATTERNS = {
    "credential_probe": re.compile(r"(credential|password|secret|token)", re.IGNORECASE),
    "exfiltration": re.compile(r"(exfiltrat|leak|dump data)", re.IGNORECASE),
    "privilege_escalation": re.compile(r"(sudo|root access|admin override)", re.IGNORECASE),
}


def detect_suspicious_query(query: str) -> Optional[str]:
    for name, pattern in SUSPICIOUS_PATTERNS.items():
        if pattern.search(query):
            return name
    return None


def audit_event(event: str, details: Optional[Dict[str, object]] = None) -> None:
    logging.getLogger("audit").info(
        event,
        extra={
            "extra": {
                "event": event,
                **(details or {}),
            }
        },
    )


def metrics_response():
    """Generate latest Prometheus metrics payload for HTTP handlers."""
    return generate_latest()


def timer() -> float:
    return time.perf_counter()

