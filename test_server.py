import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import server


class StubAgent:
    def invoke(self, payload):
        return {"output": f"stub:{payload['input']}"}


class ServerStreamingTests(unittest.TestCase):
    def setUp(self):
        server._agent = None
        server.flight_stream_manager = server.FlightStreamManager()

    def test_chat_uses_lazy_agent_initialization(self):
        with patch.dict(os.environ, {"HEALTH_PORT": "0"}, clear=False), patch.object(
            server, "AUTH_DISABLED", True
        ), patch.object(server, "_agent", StubAgent()):
            with TestClient(server.app) as client:
                response = client.post("/v1/chat", json={"prompt": "hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["response"], "stub:hello")
        self.assertIn("latency_ms", response.json())

    def test_websocket_filters_by_flight_and_priority(self):
        with patch.dict(os.environ, {"HEALTH_PORT": "0"}, clear=False), patch.object(
            server, "AUTH_DISABLED", True
        ):
            with TestClient(server.app) as client:
                with client.websocket_connect(
                    "/ws/flight-events?flight_ids=AB123&min_priority=high&scenarios=precision"
                ) as primary_stream, client.websocket_connect(
                    "/ws/flight-events?flight_ids=CD456"
                ) as secondary_stream:
                    primary_ack = primary_stream.receive_json()
                    secondary_ack = secondary_stream.receive_json()

                    publish_primary = client.post(
                        "/v1/flight-events",
                        json={
                            "flight_id": "AB123",
                            "event_type": "position_update",
                            "priority": "critical",
                            "scenario": "precision",
                            "payload": {"lat": 37.62, "lon": -122.38},
                        },
                    )
                    publish_secondary = client.post(
                        "/v1/flight-events",
                        json={
                            "flight_id": "CD456",
                            "event_type": "status_change",
                            "priority": "normal",
                            "payload": {"status": "holding"},
                        },
                    )

                    primary_event = primary_stream.receive_json()
                    secondary_event = secondary_stream.receive_json()

        self.assertEqual(primary_ack["type"], "subscribed")
        self.assertEqual(primary_ack["filters"]["flight_ids"], ["AB123"])
        self.assertEqual(secondary_ack["filters"]["flight_ids"], ["CD456"])
        self.assertEqual(publish_primary.status_code, 200)
        self.assertEqual(publish_primary.json()["delivered_subscribers"], 1)
        self.assertEqual(publish_secondary.status_code, 200)
        self.assertEqual(publish_secondary.json()["delivered_subscribers"], 1)
        self.assertEqual(primary_event["flight_id"], "AB123")
        self.assertEqual(primary_event["priority"], "critical")
        self.assertEqual(primary_event["scenario"], "precision")
        self.assertEqual(secondary_event["flight_id"], "CD456")
        self.assertEqual(secondary_event["payload"]["status"], "holding")

    def test_websocket_subscription_updates_and_ping(self):
        with patch.dict(os.environ, {"HEALTH_PORT": "0"}, clear=False), patch.object(
            server, "AUTH_DISABLED", True
        ):
            with TestClient(server.app) as client:
                with client.websocket_connect("/ws/flight-events") as websocket:
                    initial_ack = websocket.receive_json()
                    websocket.send_json(
                        {
                            "action": "subscribe",
                            "filters": {
                                "scenarios": ["stealth-edge"],
                                "priorities": ["critical"],
                            },
                        }
                    )
                    updated_ack = websocket.receive_json()
                    websocket.send_json({"action": "ping"})
                    pong = websocket.receive_json()
                    publish_response = client.post(
                        "/v1/flight-events",
                        json={
                            "flight_id": "ZX900",
                            "event_type": "signature_update",
                            "priority": "critical",
                            "scenario": "stealth-edge",
                            "payload": {"signature": "low-observable"},
                        },
                    )
                    streamed_event = websocket.receive_json()

        self.assertEqual(initial_ack["type"], "subscribed")
        self.assertEqual(updated_ack["filters"]["scenarios"], ["stealth-edge"])
        self.assertEqual(updated_ack["filters"]["priorities"], ["critical"])
        self.assertEqual(pong, {"type": "pong"})
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.json()["delivered_subscribers"], 1)
        self.assertEqual(streamed_event["event_type"], "signature_update")
        self.assertEqual(streamed_event["scenario"], "stealth-edge")


if __name__ == "__main__":
    unittest.main()
