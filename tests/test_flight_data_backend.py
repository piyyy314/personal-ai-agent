import unittest

from flight_data_backend import FlightDataService


class FlightDataServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = FlightDataService(signing_key="test-key")

    def test_ingest_normalizes_units_and_computes_overlays(self):
        snapshot = self.service.ingest(
            {
                "flight_id": "flight-001",
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
                        "source": "radar",
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
                        "source": "radar",
                    },
                ],
            }
        )

        self.assertEqual(snapshot["records_ingested"], 2)
        self.assertAlmostEqual(snapshot["latest_state"]["altitude_ft"], 4921.26, places=2)
        self.assertAlmostEqual(
            snapshot["analytics"]["performance_overlay"]["average_speed_kts"],
            410.37,
            places=2,
        )
        self.assertGreater(snapshot["analytics"]["trajectory_overlay"]["total_distance_nm"], 0.0)
        self.assertGreater(
            snapshot["analytics"]["performance_overlay"]["max_climb_rate_fpm"], 1500.0
        )

    def test_stealth_mode_redacts_identifiers_and_rounds_coordinates(self):
        snapshot = self.service.ingest(
            {
                "flight_id": "flight-002",
                "callsign": "STEALTH9",
                "tail_number": "N900ST",
                "stealth_mode": True,
                "points": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "latitude": 33.942501,
                        "longitude": -118.408123,
                        "altitude": 3200,
                        "speed": 280,
                        "heading": 90,
                        "transponder": "off",
                        "signature": 0.2,
                    }
                ],
            }
        )

        self.assertEqual(snapshot["callsign"], "*****TH9")
        self.assertEqual(snapshot["tail_number"], "***0ST")
        self.assertEqual(snapshot["latest_state"]["latitude"], 33.94)
        self.assertEqual(snapshot["latest_state"]["longitude"], -118.41)
        self.assertIn("transponder_silent", snapshot["analytics"]["alert_overlay"])
        self.assertTrue(snapshot["security"]["identifier_redacted"])

    def test_ingest_requires_at_least_one_point(self):
        with self.assertRaises(ValueError):
            self.service.ingest({"flight_id": "flight-003", "points": []})


if __name__ == "__main__":
    unittest.main()
