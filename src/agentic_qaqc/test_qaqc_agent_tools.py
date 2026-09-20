import json
import os
import tempfile
import unittest
from pathlib import Path

from qaqc_agent_tools import QAQCToolkit
from mcp_server import tool_result


class ImageToolkit(QAQCToolkit):
    def _request(self, url, method="GET"):
        return b"\x89PNG\r\nmock-image"


class QAQCToolkitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "index.json"
        self.paths = [
            "RS01SLBS/RS01SLBS-MJ01A-12-VEL3DB101_velocity_east_month_flag_local.png",
            "RS01SLBS/RS01SLBS-MJ01A-12-VEL3DB101_velocity_north_week_none_standard.svg",
            "CE02SHBP/CE02SHBP-LJ01D-05-ADCPTB104_velocity_east_day_none_full.png",
        ]
        self.cache.write_text(json.dumps(self.paths))
        self.toolkit = QAQCToolkit(cache_path=self.cache, cache_ttl_seconds=999999)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_plot_path(self):
        row = self.toolkit.parse_plot_path(self.paths[0])
        self.assertEqual(row["reference_designator"], "RS01SLBS-MJ01A-12-VEL3DB101")
        self.assertEqual(row["variable"], "velocity_east")
        self.assertEqual(row["time_span"], "month")
        self.assertEqual(row["overlay"], "flag")

    def test_search_defaults_to_rca(self):
        result = self.toolkit.search_plots(variable="velocity", limit=10)
        self.assertEqual(result["total_matches"], 2)
        self.assertTrue(all(x["site"].startswith("RS") for x in result["plots"]))

    def test_get_plot_rejects_unknown_path(self):
        self.assertFalse(self.toolkit.get_plot("missing.png")["ok"])

    def test_get_plot_can_return_mcp_image_payload(self):
        toolkit = ImageToolkit(cache_path=self.cache, cache_ttl_seconds=999999)
        result = toolkit.get_plot(self.paths[0], include_image=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["_mcp_image"]["mimeType"], "image/png")
        self.assertTrue(result["_mcp_image"]["data"].startswith("iVBOR"))
        mcp = tool_result(result)
        self.assertEqual([item["type"] for item in mcp["content"]], ["text", "image"])
        self.assertNotIn("_mcp_image", mcp["content"][0]["text"])

    def test_staged_qartod_live_sync_rejected(self):
        result = self.toolkit.pipeline_command("RS01SLBS-MJ01A-12-VEL3DB101", homebrew_qartod=True, s3_sync=True)
        self.assertFalse(result["ok"])

    def test_pipeline_plan_does_not_execute(self):
        result = self.toolkit.pipeline_command("RS01SLBS-MJ01A-12-VEL3DB101", span="30")
        self.assertTrue(result["ok"])
        self.assertFalse(result["executes"])
        self.assertIn("qaqc_pipeline", result["command"])

    def test_generate_defaults_to_plan(self):
        result = self.toolkit.generate_plots(site="RS01SLBS", span="30")
        self.assertTrue(result["ok"])
        self.assertFalse(result["executes"])

    def test_generate_execution_is_disabled_by_default(self):
        previous = os.environ.pop("QAQC_AGENT_ALLOW_PIPELINE", None)
        try:
            result = self.toolkit.generate_plots(site="RS01SLBS", execute=True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["type"], "pipeline_execution_disabled")
        finally:
            if previous is not None:
                os.environ["QAQC_AGENT_ALLOW_PIPELINE"] = previous


if __name__ == "__main__":
    unittest.main()
