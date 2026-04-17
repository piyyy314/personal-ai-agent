#!/usr/bin/env python3
"""
Health check HTTP server for Kubernetes/Docker health probes.
Runs on port 8080 to provide /health, /ready, and /metrics endpoints.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
from monitoring import health, metrics, logger


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health and metrics endpoints"""

    def log_message(self, format, *args):
        """Override to use structured logging"""
        logger.log_event(
            event_type="http_request",
            message=f"{self.address_string()} - {format % args}",
            level="debug"
        )

    def do_GET(self):
        """Handle GET requests"""
        if self.path == "/health":
            self.handle_health()
        elif self.path == "/ready":
            self.handle_ready()
        elif self.path == "/metrics":
            self.handle_metrics()
        elif self.path == "/":
            self.handle_root()
        else:
            self.send_error(404, "Not Found")

    def handle_health(self):
        """Liveness probe endpoint"""
        health_status = health.check_health()
        status_code = 200 if health_status["status"] == "healthy" else 503

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(health_status, indent=2).encode())

    def handle_ready(self):
        """Readiness probe endpoint"""
        ready_status = health.check_readiness()
        status_code = 200 if ready_status["status"] == "ready" else 503

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(ready_status, indent=2).encode())

    def handle_metrics(self):
        """Prometheus metrics endpoint"""
        metrics_data = metrics.get_prometheus_format()

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(metrics_data.encode())

    def handle_root(self):
        """Root endpoint with available endpoints"""
        info = {
            "service": "personal-ai-agent",
            "endpoints": {
                "/health": "Liveness probe",
                "/ready": "Readiness probe",
                "/metrics": "Prometheus metrics"
            }
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(info, indent=2).encode())


def start_health_server(port: int = 8080):
    """Start the health check server in a background thread"""
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.log_event(
        event_type="health_server_started",
        message=f"Health check server started on port {port}",
        level="info",
        port=port
    )
    return server


if __name__ == "__main__":
    # Run standalone for testing
    import time
    server = start_health_server()
    print("Health server running on http://localhost:8080")
    print("Endpoints: /health, /ready, /metrics")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
