from datetime import datetime, timezone
import unittest

from axial_monitoring_tools import AxialMonitoringToolkit, TOOL_SCHEMAS, dispatch


PNG = b"\x89PNG\r\n\x1a\nminimal-test-payload"


class AxialMonitoringToolsTest(unittest.TestCase):
    def setUp(self):
        self.urls = []
        def fetch(url):
            self.urls.append(url)
            if url.endswith("status/"):
                return b"<h1>Has Axial Seamount erupted yet?</h1><h1>No, not yet.</h1>"
            return PNG
        self.toolkit = AxialMonitoringToolkit(fetcher=fetch, now_fn=lambda: datetime(2026, 9, 24, tzinfo=timezone.utc))

    def test_list_streams(self):
        result = self.toolkit.list_streams()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["streams"]), 4)

    def test_fetch_allowlisted_live_plot(self):
        result = self.toolkit.get_plot("central_caldera", "bpr_7_days")
        self.assertTrue(result["ok"])
        self.assertEqual(result["instrument"], "BOTPT-A301-MJ03F")
        self.assertTrue(result["source_url"].endswith("graphs/MJ03F7DaysDET.png"))
        self.assertIn("_mcp_image", result)

    def test_rejects_unknown_stream_without_fetch(self):
        result = self.toolkit.get_plot("untrusted", "bpr_7_days")
        self.assertFalse(result["ok"])
        self.assertEqual(self.urls, [])

    def test_current_status(self):
        result = self.toolkit.current_status()
        self.assertTrue(result["ok"])
        self.assertEqual(result["eruption_status"], "no")

    def test_schemas_and_dispatch(self):
        self.assertEqual(len(TOOL_SCHEMAS), 3)
        self.assertTrue(dispatch(self.toolkit, "axial_monitoring_list_streams", {})["ok"])


if __name__ == "__main__":
    unittest.main()
