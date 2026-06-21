import io
import json
import logging
import os
import stat
import tempfile
import unittest
from unittest.mock import patch

from monitoring import JsonFormatter, StructuredLogger, audit_event, configure_logging, detect_suspicious_query


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_stream_for(structured_logger: StructuredLogger) -> io.StringIO:
    """Replace all handlers on structured_logger.logger with a single in-memory
    StringIO handler using JsonFormatter, and return that stream."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    structured_logger.logger.handlers = [handler]
    structured_logger.logger.propagate = False
    return stream


def _parse_log_message(stream: io.StringIO) -> dict:
    """Parse the outer JSON emitted by JsonFormatter and return the inner
    structured dict stored in the 'message' field by log_event."""
    outer = json.loads(stream.getvalue().strip())
    return json.loads(outer["message"])


class StructuredLoggerInitTests(unittest.TestCase):
    """Tests for StructuredLogger.__init__ (new in this PR)."""

    def _unique_name(self, suffix: str = "") -> str:
        return f"test_sl_{id(self)}_{suffix}"

    def test_init_creates_console_handler_with_json_formatter(self):
        with tempfile.TemporaryDirectory() as log_dir:
            with patch.dict(os.environ, {"LOG_DIR": log_dir}):
                sl = StructuredLogger(self._unique_name("console"))
        stream_handlers = [
            h for h in sl.logger.handlers if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        self.assertGreaterEqual(len(stream_handlers), 1)
        self.assertIsInstance(stream_handlers[0].formatter, JsonFormatter)

    def test_init_creates_file_handler_when_log_dir_is_writable(self):
        with tempfile.TemporaryDirectory() as log_dir:
            with patch.dict(os.environ, {"LOG_DIR": log_dir}):
                sl = StructuredLogger(self._unique_name("file"))
            file_handlers = [h for h in sl.logger.handlers if isinstance(h, logging.FileHandler)]
            self.assertEqual(len(file_handlers), 1)
            self.assertTrue(file_handlers[0].baseFilename.endswith("audit.log"))
            # Clean up file handler to avoid ResourceWarning
            file_handlers[0].close()

    def test_init_falls_back_to_console_only_when_log_dir_unwritable(self):
        with tempfile.TemporaryDirectory() as log_dir:
            unwritable = os.path.join(log_dir, "noaccess")
            os.makedirs(unwritable)
            os.chmod(unwritable, stat.S_IREAD | stat.S_IEXEC)
            try:
                log_path = os.path.join(unwritable, "subdir")
                with patch.dict(os.environ, {"LOG_DIR": log_path}):
                    sl = StructuredLogger(self._unique_name("fallback"))
                file_handlers = [h for h in sl.logger.handlers if isinstance(h, logging.FileHandler)]
                self.assertEqual(len(file_handlers), 0)
            finally:
                os.chmod(unwritable, stat.S_IRWXU)

    def test_init_default_log_level_is_info(self):
        with tempfile.TemporaryDirectory() as log_dir:
            with patch.dict(os.environ, {"LOG_DIR": log_dir}):
                sl = StructuredLogger(self._unique_name("level_default"))
        self.assertEqual(sl.logger.level, logging.INFO)

    def test_init_accepts_custom_log_level(self):
        with tempfile.TemporaryDirectory() as log_dir:
            with patch.dict(os.environ, {"LOG_DIR": log_dir}):
                sl = StructuredLogger(self._unique_name("level_debug"), log_level="DEBUG")
        self.assertEqual(sl.logger.level, logging.DEBUG)

    def test_init_log_level_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as log_dir:
            with patch.dict(os.environ, {"LOG_DIR": log_dir}):
                sl = StructuredLogger(self._unique_name("level_warning"), log_level="warning")
        self.assertEqual(sl.logger.level, logging.WARNING)

    def test_init_reads_log_dir_from_env(self):
        with tempfile.TemporaryDirectory() as log_dir:
            with patch.dict(os.environ, {"LOG_DIR": log_dir}):
                sl = StructuredLogger(self._unique_name("env_dir"))
            file_handlers = [h for h in sl.logger.handlers if isinstance(h, logging.FileHandler)]
            self.assertEqual(len(file_handlers), 1)
            self.assertTrue(file_handlers[0].baseFilename.startswith(log_dir))
            file_handlers[0].close()


class StructuredLoggerLogEventTests(unittest.TestCase):
    """Tests for StructuredLogger.log_event (new in this PR)."""

    def setUp(self):
        self._log_dir = tempfile.mkdtemp()
        with patch.dict(os.environ, {"LOG_DIR": self._log_dir}):
            self.sl = StructuredLogger(f"test_log_event_{id(self)}")
        self.stream = _capture_stream_for(self.sl)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._log_dir, ignore_errors=True)

    def test_log_event_includes_required_fields(self):
        self.sl.log_event("user_action", "User performed an action")
        data = _parse_log_message(self.stream)
        self.assertIn("timestamp", data)
        self.assertEqual(data["event_type"], "user_action")
        self.assertEqual(data["message"], "User performed an action")
        self.assertIn("user_id", data)
        self.assertIn("session_id", data)
        self.assertIn("metadata", data)

    def test_log_event_default_user_id_is_system(self):
        self.sl.log_event("ping", "health check")
        data = _parse_log_message(self.stream)
        self.assertEqual(data["user_id"], "system")

    def test_log_event_default_session_id_is_none(self):
        self.sl.log_event("ping", "health check")
        data = _parse_log_message(self.stream)
        self.assertIsNone(data["session_id"])

    def test_log_event_propagates_user_id_and_session_id_from_kwargs(self):
        self.sl.log_event(
            "query",
            "A user query",
            user_id="alice",
            session_id="sess-42",
        )
        data = _parse_log_message(self.stream)
        self.assertEqual(data["user_id"], "alice")
        self.assertEqual(data["session_id"], "sess-42")

    def test_log_event_stores_extra_kwargs_in_metadata(self):
        self.sl.log_event("data_access", "Accessed records", resource="db", count=5)
        data = _parse_log_message(self.stream)
        self.assertEqual(data["metadata"]["resource"], "db")
        self.assertEqual(data["metadata"]["count"], 5)

    def test_log_event_timestamp_is_iso_format(self):
        self.sl.log_event("tick", "timer event")
        data = _parse_log_message(self.stream)
        from datetime import datetime
        # Should not raise
        datetime.fromisoformat(data["timestamp"])

    def test_log_event_routes_to_warning_level(self):
        self.sl.log_event("anomaly", "Something odd", level="warning")
        outer = json.loads(self.stream.getvalue().strip())
        self.assertEqual(outer["level"], "WARNING")

    def test_log_event_routes_to_error_level(self):
        self.sl.log_event("failure", "Critical failure", level="error")
        outer = json.loads(self.stream.getvalue().strip())
        self.assertEqual(outer["level"], "ERROR")

    def test_log_event_default_level_is_info(self):
        self.sl.log_event("default_level", "check default level")
        outer = json.loads(self.stream.getvalue().strip())
        self.assertEqual(outer["level"], "INFO")

    def test_log_event_empty_message_is_allowed(self):
        self.sl.log_event("empty_msg", "")
        data = _parse_log_message(self.stream)
        self.assertEqual(data["message"], "")

    def test_log_event_empty_event_type_is_allowed(self):
        self.sl.log_event("", "some message")
        data = _parse_log_message(self.stream)
        self.assertEqual(data["event_type"], "")


class StructuredLoggerAuditLogTests(unittest.TestCase):
    """Tests for StructuredLogger.audit_log (new in this PR)."""

    def setUp(self):
        self._log_dir = tempfile.mkdtemp()
        with patch.dict(os.environ, {"LOG_DIR": self._log_dir}):
            self.sl = StructuredLogger(f"test_audit_log_{id(self)}")
        self.stream = _capture_stream_for(self.sl)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._log_dir, ignore_errors=True)

    def test_audit_log_sets_event_type_to_audit(self):
        self.sl.audit_log("read", "records_db", "success")
        data = _parse_log_message(self.stream)
        self.assertEqual(data["event_type"], "audit")

    def test_audit_log_formats_message_correctly(self):
        self.sl.audit_log("delete", "user_table", "denied")
        data = _parse_log_message(self.stream)
        self.assertEqual(data["message"], "delete on user_table: denied")

    def test_audit_log_uses_info_level(self):
        self.sl.audit_log("export", "report", "success")
        outer = json.loads(self.stream.getvalue().strip())
        self.assertEqual(outer["level"], "INFO")

    def test_audit_log_passes_action_resource_outcome_in_metadata(self):
        self.sl.audit_log("update", "config", "success")
        data = _parse_log_message(self.stream)
        self.assertEqual(data["metadata"]["action"], "update")
        self.assertEqual(data["metadata"]["resource"], "config")
        self.assertEqual(data["metadata"]["outcome"], "success")

    def test_audit_log_propagates_extra_kwargs(self):
        self.sl.audit_log("login", "auth_service", "success", user_id="bob", ip="10.0.0.1")
        data = _parse_log_message(self.stream)
        self.assertEqual(data["user_id"], "bob")
        self.assertEqual(data["metadata"]["ip"], "10.0.0.1")

    def test_audit_log_with_failed_outcome(self):
        self.sl.audit_log("write", "sensitive_file", "failed")
        data = _parse_log_message(self.stream)
        self.assertEqual(data["message"], "write on sensitive_file: failed")
        self.assertEqual(data["metadata"]["outcome"], "failed")

    def test_audit_log_boundary_empty_strings(self):
        self.sl.audit_log("", "", "")
        data = _parse_log_message(self.stream)
        self.assertEqual(data["event_type"], "audit")
        self.assertEqual(data["message"], " on : ")

