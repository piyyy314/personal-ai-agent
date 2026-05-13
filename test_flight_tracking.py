#!/usr/bin/env python3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from flight_tracking import FlightHistoryStore, FlightObservation


class FlightHistoryStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage_path = f"{self.tempdir.name}/history.jsonl"
        self.store = FlightHistoryStore(storage_path=self.storage_path)
        self.start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def observation(
        self,
        aircraft_id: str,
        minutes: int,
        latitude: float,
        longitude: float,
        **kwargs,
    ) -> FlightObservation:
        return FlightObservation(
            aircraft_id=aircraft_id,
            timestamp=self.start + timedelta(minutes=minutes),
            latitude=latitude,
            longitude=longitude,
            **kwargs,
        )

    def test_replay_sorts_history_and_respects_sampling_interval(self) -> None:
        self.store.record(self.observation("N12345", 2, 38.9, -77.03, altitude_ft=12000))
        self.store.record(self.observation("N12345", 0, 38.8, -77.0, altitude_ft=10000))
        self.store.record(self.observation("N12345", 1, 38.85, -77.01, altitude_ft=11000))

        replay = self.store.replay("N12345", interval_seconds=90)

        self.assertEqual(replay["frame_count"], 2)
        self.assertEqual(
            [frame["offset_seconds"] for frame in replay["frames"]],
            [0, 120],
        )
        self.assertEqual(replay["summary"]["position_count"], 3)
        self.assertEqual(replay["start_time"], "2026-01-01T12:00:00Z")
        self.assertEqual(replay["end_time"], "2026-01-01T12:02:00Z")
        self.assertGreater(replay["summary"]["estimated_distance_nm"], 0)

    def test_timeline_surfaces_visual_layers_and_anomalies(self) -> None:
        self.store.record(
            self.observation(
                "EAGLE1",
                0,
                38.8,
                -77.0,
                altitude_ft=10000,
                squawk="7700",
                event_type="alert",
            )
        )
        self.store.record(
            self.observation(
                "EAGLE1",
                4,
                38.81,
                -77.02,
                altitude_ft=17000,
            )
        )
        self.store.record(
            self.observation(
                "EAGLE1",
                40,
                38.85,
                -77.08,
                altitude_ft=18000,
                event_type="handoff",
            )
        )

        replay = self.store.replay("EAGLE1")
        timeline = self.store.timeline(aircraft_id="EAGLE1")

        anomaly_types = {anomaly["type"] for anomaly in replay["anomalies"]}
        self.assertIn("emergency_squawk", anomaly_types)
        self.assertIn("rapid_altitude_change", anomaly_types)
        self.assertEqual(timeline["aircraft_count"], 1)
        self.assertEqual(len(timeline["visual_layers"]["activity_windows"]), 2)
        self.assertEqual(
            timeline["visual_layers"]["event_markers"][0]["event_type"],
            "alert",
        )
        self.assertGreaterEqual(len(timeline["visual_layers"]["altitude_bands"]), 2)

    def test_store_reloads_persisted_history(self) -> None:
        self.store.record(self.observation("FALCON9", 0, 34.0, -118.4, altitude_ft=5000))

        reloaded = FlightHistoryStore(storage_path=self.storage_path)
        replay = reloaded.replay("FALCON9")

        self.assertEqual(replay["frame_count"], 1)
        self.assertEqual(replay["frames"][0]["aircraft_id"], "FALCON9")


if __name__ == "__main__":
    unittest.main()
