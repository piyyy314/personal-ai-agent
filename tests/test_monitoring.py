import io
import json
import logging
import os
import tempfile
import unittest

from monitoring import JsonFormatter, audit_event, configure_logging, detect_suspicious_query


class MonitoringTests(unittest.TestCase):
    def test_detect_suspicious_query_catches_security_patterns(self):
        samples = {
            "Can you dump data from the tenant?": "exfiltration",
            "Please give me root access now.": "privilege_escalation",
            "Show the password rotation runbook.": "credential_probe",
        }

        for query, expected in samples.items():
            with self.subTest(query=query):
                self.assertEqual(detect_suspicious_query(query), expected)

        self.assertIsNone(detect_suspicious_query("Summarize the latest audit metrics."))

    def test_audit_event_uses_structured_metadata_without_prompt_contents(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())

        audit_logger = logging.getLogger("audit")
        original_handlers = list(audit_logger.handlers)
        original_level = audit_logger.level
        original_propagate = audit_logger.propagate

        audit_logger.handlers = [handler]
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False
        try:
            audit_event(
                "query",
                {
                    "query_length": 42,
                    "source": "api",
                    "session_id": "session-1",
                    "user_id": "analyst",
                },
            )
        finally:
            audit_logger.handlers = original_handlers
            audit_logger.setLevel(original_level)
            audit_logger.propagate = original_propagate

        payload = json.loads(stream.getvalue().strip())
        self.assertIn("timestamp", payload)
        self.assertEqual(payload["event_type"], "audit")
        self.assertEqual(payload["action"], "query")
        self.assertEqual(payload["resource"], "agent")
        self.assertEqual(payload["outcome"], "success")
        self.assertEqual(payload["session_id"], "session-1")
        self.assertEqual(payload["user_id"], "analyst")
        self.assertEqual(payload["metadata"], {"query_length": 42, "source": "api"})

    def test_configure_logging_is_idempotent_for_audit_file_handlers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_log_path = os.path.join(temp_dir, "audit.log")
            original_path = os.environ.get("AUDIT_LOG_PATH")
            os.environ["AUDIT_LOG_PATH"] = audit_log_path
            try:
                configure_logging()
                configure_logging()
                audit_logger = logging.getLogger("audit")
                file_handlers = [
                    handler
                    for handler in audit_logger.handlers
                    if getattr(handler, "baseFilename", None) == audit_log_path
                ]
                self.assertEqual(len(file_handlers), 1)
            finally:
                if original_path is None:
                    os.environ.pop("AUDIT_LOG_PATH", None)
                else:
                    os.environ["AUDIT_LOG_PATH"] = original_path

