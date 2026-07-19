import json
import unittest
import urllib.error
import urllib.request

from health_server import start_health_server
from monitoring import is_session_running, set_session_status


class HealthServerTests(unittest.TestCase):
    def test_health_server_exposes_health_ready_metrics_and_root(self):
        server = start_health_server(port=0)
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"
        original_status = is_session_running()

        try:
            set_session_status(False)

            with urllib.request.urlopen(f"{base_url}/health") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response), {"status": "healthy"})

            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(f"{base_url}/ready")
            self.assertEqual(error.exception.code, 503)
            self.assertEqual(json.loads(error.exception.read().decode()), {"status": "not_ready"})

            set_session_status(True)
            with urllib.request.urlopen(f"{base_url}/ready") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response), {"status": "ready"})

            with urllib.request.urlopen(f"{base_url}/") as response:
                payload = json.load(response)
                self.assertIn("/metrics", payload["endpoints"])

            with urllib.request.urlopen(f"{base_url}/metrics") as response:
                metrics_payload = response.read().decode()
                self.assertIn("agent_session_status", metrics_payload)
        finally:
            set_session_status(original_status)
            server.shutdown()
            server.server_close()
