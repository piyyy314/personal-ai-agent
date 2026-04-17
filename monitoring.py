#!/usr/bin/env python3
"""
Monitoring and metrics collection module.
Provides Prometheus metrics, health checks, and structured logging.
"""
import logging
import time
import os
from datetime import datetime
from typing import Dict, Any
import json

# Configure structured logging
class StructuredLogger:
    """Structured logger for compliance and audit requirements"""

    def __init__(self, name: str, log_level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper()))

        # Console handler with JSON formatting
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)

        # File handler for audit logs
        audit_handler = logging.FileHandler("/var/log/agent/audit.log")
        audit_handler.setFormatter(JsonFormatter())
        self.logger.addHandler(audit_handler)

    def log_event(self, event_type: str, message: str, level: str = "info", **kwargs):
        """Log structured event with metadata"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "message": message,
            "user_id": kwargs.get("user_id", "system"),
            "session_id": kwargs.get("session_id"),
            "metadata": kwargs
        }

        log_func = getattr(self.logger, level.lower())
        log_func(json.dumps(log_data))

    def audit_log(self, action: str, resource: str, outcome: str, **kwargs):
        """Log audit events for compliance"""
        self.log_event(
            event_type="audit",
            message=f"{action} on {resource}: {outcome}",
            level="info",
            action=action,
            resource=resource,
            outcome=outcome,
            **kwargs
        )


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging"""

    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        if hasattr(record, 'exc_info') and record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class MetricsCollector:
    """Prometheus-compatible metrics collector"""

    def __init__(self):
        self.metrics: Dict[str, Any] = {
            "requests_total": 0,
            "requests_failed": 0,
            "requests_success": 0,
            "response_time_sum": 0.0,
            "response_time_count": 0,
            "active_sessions": 0,
            "errors_by_type": {},
            "api_calls_by_provider": {},
            "compliance_violations": 0,
            "security_events": 0,
        }
        self.start_time = time.time()

    def increment(self, metric: str, value: float = 1.0, labels: Dict[str, str] = None):
        """Increment a counter metric"""
        if metric not in self.metrics:
            self.metrics[metric] = 0
        self.metrics[metric] += value

    def observe(self, metric: str, value: float, labels: Dict[str, str] = None):
        """Observe a value (for histograms/summaries)"""
        sum_key = f"{metric}_sum"
        count_key = f"{metric}_count"

        if sum_key not in self.metrics:
            self.metrics[sum_key] = 0.0
        if count_key not in self.metrics:
            self.metrics[count_key] = 0

        self.metrics[sum_key] += value
        self.metrics[count_key] += 1

    def set_gauge(self, metric: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge metric"""
        self.metrics[metric] = value

    def get_metrics(self) -> Dict[str, Any]:
        """Get all metrics in Prometheus exposition format"""
        return self.metrics.copy()

    def get_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format"""
        lines = []

        # Add HELP and TYPE comments
        lines.append("# HELP agent_requests_total Total number of requests")
        lines.append("# TYPE agent_requests_total counter")
        lines.append(f"agent_requests_total {self.metrics['requests_total']}")

        lines.append("# HELP agent_requests_failed Failed requests")
        lines.append("# TYPE agent_requests_failed counter")
        lines.append(f"agent_requests_failed {self.metrics['requests_failed']}")

        lines.append("# HELP agent_requests_success Successful requests")
        lines.append("# TYPE agent_requests_success counter")
        lines.append(f"agent_requests_success {self.metrics['requests_success']}")

        lines.append("# HELP agent_active_sessions Active sessions")
        lines.append("# TYPE agent_active_sessions gauge")
        lines.append(f"agent_active_sessions {self.metrics['active_sessions']}")

        lines.append("# HELP agent_uptime_seconds Agent uptime in seconds")
        lines.append("# TYPE agent_uptime_seconds counter")
        lines.append(f"agent_uptime_seconds {time.time() - self.start_time}")

        lines.append("# HELP agent_compliance_violations Compliance violations detected")
        lines.append("# TYPE agent_compliance_violations counter")
        lines.append(f"agent_compliance_violations {self.metrics['compliance_violations']}")

        lines.append("# HELP agent_security_events Security events detected")
        lines.append("# TYPE agent_security_events counter")
        lines.append(f"agent_security_events {self.metrics['security_events']}")

        # Response time histogram
        if self.metrics['response_time_count'] > 0:
            avg_response = self.metrics['response_time_sum'] / self.metrics['response_time_count']
            lines.append("# HELP agent_response_time_seconds Response time in seconds")
            lines.append("# TYPE agent_response_time_seconds summary")
            lines.append(f"agent_response_time_seconds_sum {self.metrics['response_time_sum']}")
            lines.append(f"agent_response_time_seconds_count {self.metrics['response_time_count']}")

        return "\n".join(lines) + "\n"


class HealthChecker:
    """Health check system for container orchestration"""

    def __init__(self):
        self.checks = {}
        self.status = "healthy"

    def register_check(self, name: str, check_func):
        """Register a health check function"""
        self.checks[name] = check_func

    def check_health(self) -> Dict[str, Any]:
        """Run all health checks"""
        results = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }

        all_healthy = True
        for name, check_func in self.checks.items():
            try:
                check_result = check_func()
                results["checks"][name] = {
                    "status": "pass" if check_result else "fail",
                    "details": check_result
                }
                if not check_result:
                    all_healthy = False
            except Exception as e:
                results["checks"][name] = {
                    "status": "fail",
                    "error": str(e)
                }
                all_healthy = False

        results["status"] = "healthy" if all_healthy else "unhealthy"
        return results

    def check_readiness(self) -> Dict[str, Any]:
        """Check if service is ready to accept traffic"""
        # Basic readiness checks
        ready = {
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {
                "environment": os.getenv("OPENAI_API_KEY") is not None or os.getenv("OLLAMA_MODEL") is not None,
                "disk_space": self._check_disk_space(),
                "memory": self._check_memory()
            }
        }

        if not all(ready["checks"].values()):
            ready["status"] = "not_ready"

        return ready

    def _check_disk_space(self) -> bool:
        """Check available disk space"""
        try:
            import shutil
            stat = shutil.disk_usage("/")
            free_pct = (stat.free / stat.total) * 100
            return free_pct > 10  # At least 10% free
        except:
            return True  # Assume OK if check fails

    def _check_memory(self) -> bool:
        """Check available memory"""
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        meminfo[parts[0].rstrip(':')] = int(parts[1])

                if 'MemAvailable' in meminfo and 'MemTotal' in meminfo:
                    available_pct = (meminfo['MemAvailable'] / meminfo['MemTotal']) * 100
                    return available_pct > 10  # At least 10% available
        except:
            return True  # Assume OK if check fails

        return True


# Global instances
logger = StructuredLogger("agent", os.getenv("LOG_LEVEL", "INFO"))
metrics = MetricsCollector()
health = HealthChecker()
