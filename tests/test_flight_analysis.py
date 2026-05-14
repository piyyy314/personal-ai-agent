import unittest

from flight_analysis import analyze_flight_operations, filter_flights, search_records


FLIGHTS = [
    {
        "id": "F-001",
        "callsign": "RAVEN1",
        "origin": "LAX",
        "destination": "LAS",
        "operator": "Night Watch",
        "status": "loitering",
        "altitude": 4500,
        "speed": 420,
        "squawk": "7700",
        "tags": ["watch", "priority"],
        "latitude": 34.1,
        "longitude": -118.2,
        "timestamp": "2026-05-13T01:00:00Z",
    },
    {
        "id": "F-002",
        "callsign": "SUNRISE7",
        "origin": "SEA",
        "destination": "DEN",
        "operator": "SkyLink",
        "status": "cruise",
        "altitude": 32000,
        "speed": 460,
        "tags": ["routine"],
        "latitude": 47.4,
        "longitude": -122.3,
        "timestamp": "2026-05-13T02:00:00Z",
    },
]

EVENTS = [
    {
        "id": "E-1",
        "event_type": "surveillance",
        "severity": "high",
        "description": "Target entered restricted corridor",
        "timestamp": "2026-05-13T01:15:00Z",
    }
]


class FlightAnalysisTests(unittest.TestCase):
    def test_filter_flights_supports_ranges_tags_and_bounds(self):
        results = filter_flights(
            FLIGHTS,
            {
                "origin": "LAX",
                "ranges": {"altitude": {"max": 5000}},
                "tags_any": ["watch"],
                "map_bounds": {
                    "north": 35,
                    "south": 33,
                    "east": -118,
                    "west": -119,
                },
            },
        )
        self.assertEqual([flight["id"] for flight in results], ["F-001"])

    def test_search_records_ranks_flight_and_event_matches(self):
        results = search_records(FLIGHTS, EVENTS, "restricted raven", limit=5)
        self.assertEqual(results["total_matches"], 2)
        self.assertEqual(results["results"][0]["record_type"], "event")
        self.assertEqual(results["results"][1]["record_type"], "flight")

    def test_analyze_flight_operations_builds_overlays(self):
        analysis = analyze_flight_operations(
            FLIGHTS,
            EVENTS,
            filters={"flagged_only": True},
            search_query="surveillance",
        )
        self.assertEqual(len(analysis["filtered_flights"]), 1)
        self.assertEqual(
            analysis["overlays"]["summary"],
            {
                "flight_count": 1,
                "event_count": 1,
                "flagged_flights": 1,
                "flagged_events": 1,
            },
        )
        self.assertEqual(
            analysis["overlays"]["threat_signals"][0]["signals"][0],
            "emergency_squawk_7700",
        )
        self.assertEqual(analysis["search"]["results"][0]["record_type"], "event")


if __name__ == "__main__":
    unittest.main()
