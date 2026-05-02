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


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH")
METRICS_PORT = int(os.getenv("METRICS_PORT", "9000"))
METRICS_HOST = os.getenv("METRICS_HOST", "0.0.0.0")


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
    formatter = JsonFormatter()
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(LOG_LEVEL)
    root.addHandler(stream_handler)

    audit_logger = logging.getLogger("audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = True
    if AUDIT_LOG_PATH:
        audit_log_dir = os.path.dirname(AUDIT_LOG_PATH)
        try:
            if audit_log_dir:
                os.makedirs(audit_log_dir, exist_ok=True)
            file_handler = logging.FileHandler(AUDIT_LOG_PATH)
            file_handler.setFormatter(formatter)
            audit_logger.addHandler(file_handler)
        except OSError as exc:
            root.warning(
                "Failed to initialize audit file logging; continuing with stdout-only logging.",
                extra={"extra": {"audit_log_path": AUDIT_LOG_PATH, "error": str(exc)}},
            )


def start_metrics_server(host: str = METRICS_HOST, port: int = METRICS_PORT) -> None:
    """
    Launch a Prometheus metrics HTTP server (CLI mode).
    FastAPI mode uses the /metrics endpoint instead.
    """
    # start_http_server is idempotent enough for single-process usage.
    start_http_server(port, addr=host)


def set_session_status(running: bool) -> None:
    SESSION_HEALTH.set(1 if running else 0)


def record_request_outcome(status: str, duration_seconds: float, source: str) -> None:
    REQUEST_COUNTER.labels(status=status, source=source).inc()
    REQUEST_LATENCY.labels(source=source).observe(duration_seconds)


def record_security_event(event_type: str) -> None:
    SECURITY_EVENTS.labels(event_type=event_type).inc()


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

