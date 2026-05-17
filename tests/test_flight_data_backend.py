#!/usr/bin/env python3
"""Tests for flight_data_backend.FlightDataService.

Covers the key correctness and security fixes:
- Out-of-order telemetry is sorted before processing.
- Signing key is required (ValueError raised when absent).
- Stealth mode redacts identifiers and excludes metadata.
- Integrity hash corresponds to the redacted payload.
- Memory bounds (MAX_FLIGHTS, MAX_POINTS_PER_FLIGHT) are respected.
"""
import unittest

from flight_data_backend import (
    MAX_FLIGHTS,
    MAX_POINTS_PER_FLIGHT,
    FlightDataService,
)


def _make_service(**kwargs) -> FlightDataService:
    """Return a service with a test signing key."""
    kwargs.setdefault("signing_key", "test-signing-key-for-unit-tests")
    return FlightDataService(**kwargs)


class TestSigningKeyRequired(unittest.TestCase):
    def test_raises_without_signing_key(self):
        with self.assertRaises((ValueError, TypeError)):
            FlightDataService(signing_key=None)  # type: ignore[arg-type]

    def test_raises_with_empty_signing_key(self):
        with self.assertRaises(ValueError):
            FlightDataService(signing_key="")


class TestIngestNormalisesUnits(unittest.TestCase):
    def setUp(self):
        self.svc = _make_service()

    def test_ingest_basic(self):
        snap = self.svc.ingest({
            "flight_id": "FL001",
            "callsign": "N123AA",
            "points": [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "latitude": 34.0,
                    "longitude": -118.0,
                    "altitude": 1000,
                    "altitude_unit": "m",
                    "speed": 740,
                    "speed_unit": "kmh",
                    "heading": 90,
                },
                {
                    "timestamp": "2026-01-01T00:01:00Z",
                    "latitude": 34.05,
                    "longitude": -117.95,
                    "altitude": 1500,
                    "altitude_unit": "m",
                    "speed": 780,
                    "speed_unit": "kmh",
                    "heading": 95,
                },
            ],
        })
        self.assertEqual(snap["records_ingested"], 2)
        self.assertAlmostEqual(snap["latest_state"]["altitude_ft"], 4921.26, places=2)
        self.assertGreater(snap["analytics"]["trajectory_overlay"]["total_distance_nm"], 0.0)
        self.assertIn("security", snap)
        self.assertIn("integrity_hash", snap["security"])


class TestOutOfOrderTelemetry(unittest.TestCase):
    """Batches arriving out of chronological order must be sorted first."""

    def setUp(self):
        self.svc = _make_service()

    def test_latest_state_is_chronologically_last(self):
        snap = self.svc.ingest({
            "flight_id": "FL-OOOT",
            "callsign": "OOO001",
            "points": [
                # Second point submitted first
                {
                    "timestamp": "2026-01-01T00:02:00Z",
                    "latitude": 34.10,
                    "longitude": -117.90,
                    "altitude": 12000,
                    "speed": 450,
                    "heading": 90,
                },
                # First point submitted second
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "latitude": 34.00,
                    "longitude": -118.00,
                    "altitude": 10000,
                    "speed": 400,
                    "heading": 88,
                },
            ],
        })
        # latest_state should reflect the 00:02 point (higher altitude/lat)
        self.assertAlmostEqual(snap["latest_state"]["altitude_ft"], 12000.0, places=0)
        self.assertAlmostEqual(snap["latest_state"]["latitude"], 34.10, places=4)


class TestStealthModeRedaction(unittest.TestCase):
    def setUp(self):
        self.svc = _make_service()

    def test_identifiers_redacted(self):
        snap = self.svc.ingest({
            "flight_id": "FL-STEALTH",
            "callsign": "STEALTH9",
            "tail_number": "N900ST",
            "stealth_mode": True,
            "metadata": {"secret_field": "classified"},
            "points": [{
                "timestamp": "2026-01-01T00:00:00Z",
                "latitude": 33.942501,
                "longitude": -118.408123,
                "altitude": 3200,
                "speed": 280,
                "heading": 90,
            }],
        })
        # Callsign and tail should be masked
        self.assertIn("*", snap["callsign"])
        self.assertIn("*", snap["tail_number"])
        # Metadata must be excluded (not leaked) in stealth mode
        self.assertEqual(snap.get("metadata", {}), {})
        # Coordinates rounded to 2 decimal places
        self.assertEqual(snap["latest_state"]["latitude"], round(33.942501, 2))
        self.assertEqual(snap["latest_state"]["longitude"], round(-118.408123, 2))

    def test_integrity_hash_matches_redacted_payload(self):
        """Hash must be computed *after* masking so it corresponds to the returned payload."""
        import hashlib
        import hmac
        import json

        snap = self.svc.ingest({
            "flight_id": "FL-HASH",
            "callsign": "CLASSIFIED",
            "stealth_mode": True,
            "points": [{
                "timestamp": "2026-01-01T00:00:00Z",
                "latitude": 40.0,
                "longitude": -75.0,
                "altitude": 20000,
                "speed": 500,
                "heading": 180,
            }],
        })
        # Recompute hash over the payload excluding the security field itself
        payload_without_security = {k: v for k, v in snap.items() if k != "security"}
        serialised = json.dumps(
            payload_without_security, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        key = b"test-signing-key-for-unit-tests"
        expected = hmac.new(key, serialised, hashlib.sha256).hexdigest()
        self.assertEqual(snap["security"]["integrity_hash"], expected)


class TestBoundedGrowth(unittest.TestCase):
    def test_points_per_flight_bounded(self):
        svc = _make_service()
        # Ingest more than MAX_POINTS_PER_FLIGHT points across multiple batches
        batch_size = 50
        batches = (MAX_POINTS_PER_FLIGHT // batch_size) + 3
        base_ts = 1_000_000  # seconds since epoch offset
        for batch in range(batches):
            points = []
            for i in range(batch_size):
                total_sec = base_ts + batch * batch_size * 60 + i * 60
                h = (total_sec // 3600) % 24
                m = (total_sec // 60) % 60
                s = total_sec % 60
                day = (total_sec // 86400) % 28 + 1  # keep day in 1..28
                points.append({
                    "timestamp": f"2026-01-{day:02d}T{h:02d}:{m:02d}:{s:02d}Z",
                    "latitude": 34.0,
                    "longitude": -118.0,
                    "altitude": 10000,
                    "speed": 400,
                    "heading": 90,
                })
            svc.ingest({"flight_id": "FL-BOUNDED", "callsign": "BND001", "points": points})

        # Internal point count should not exceed the cap
        stored = svc._store["FL-BOUNDED"]  # type: ignore[index]
        self.assertLessEqual(len(stored["normalized_points"]), MAX_POINTS_PER_FLIGHT)

    def test_total_flights_bounded(self):
        svc = _make_service()
        # Fill up to the limit
        for i in range(MAX_FLIGHTS + 10):
            svc.ingest({
                "flight_id": f"FL{i:06d}",
                "points": [{
                    "timestamp": "2026-01-01T00:00:00Z",
                    "latitude": 0.0,
                    "longitude": 0.0,
                    "altitude": 10000,
                    "speed": 300,
                    "heading": 0,
                }],
            })
        self.assertLessEqual(len(svc._store), MAX_FLIGHTS)  # type: ignore[arg-type]


class TestFlightIdValidation(unittest.TestCase):
    def test_flight_id_stored_correctly(self):
        svc = _make_service()
        snap = svc.ingest({
            "flight_id": "FL-VALID.ID-123",
            "points": [{
                "timestamp": "2026-01-01T00:00:00Z",
                "latitude": 0.0,
                "longitude": 0.0,
                "altitude": 5000,
                "speed": 300,
                "heading": 90,
            }],
        })
        self.assertEqual(snap["flight_id"], "FL-VALID.ID-123")
        retrieved = svc.get_flight("FL-VALID.ID-123")
        self.assertEqual(retrieved["flight_id"], "FL-VALID.ID-123")

    def test_unknown_flight_raises_key_error(self):
        svc = _make_service()
        with self.assertRaises(KeyError):
            svc.get_flight("nonexistent")


if __name__ == "__main__":
    unittest.main()
