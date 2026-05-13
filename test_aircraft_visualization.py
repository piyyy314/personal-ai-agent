import unittest

from aircraft_visualization import (
    AircraftSnapshot,
    build_aircraft_analysis,
    normalize_heading,
    render_aircraft_visualization,
)


class AircraftVisualizationTests(unittest.TestCase):
    def test_heading_is_normalized_into_compass_range(self):
        self.assertEqual(normalize_heading(725), 5)
        self.assertEqual(normalize_heading(-90), 270)

    def test_analysis_reports_advanced_and_security_views(self):
        analysis = build_aircraft_analysis(
            AircraftSnapshot(
                altitude_ft=450,
                speed_kts=410,
                heading_deg=210,
                stealth_enabled=False,
            )
        )

        self.assertEqual(analysis["advanced"]["altitude_band"], "nap-of-earth")
        self.assertEqual(analysis["basic"]["heading_sector"], "SW")
        self.assertEqual(analysis["security"]["exposure_level"], "medium")
        self.assertIn(
            "Stealth disabled increases radar exposure.", analysis["security"]["flags"]
        )
        self.assertIn(
            "Low-altitude/high-speed ingress compresses reaction time.",
            analysis["security"]["flags"],
        )

    def test_html_render_contains_visualization_modules(self):
        html = render_aircraft_visualization(
            AircraftSnapshot(
                altitude_ft=38000,
                speed_kts=520,
                heading_deg=45,
                stealth_enabled=True,
            )
        )

        self.assertIn("Altitude Module", html)
        self.assertIn("Speed Module", html)
        self.assertIn("Heading Module", html)
        self.assertIn("Stealth Module", html)
        self.assertIn("Security-Focused View", html)


if __name__ == "__main__":
    unittest.main()
