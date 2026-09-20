import json, tempfile, unittest
from pathlib import Path
from mcp_server import tool_result
from nereus_agent_tools import NereusToolkit, TOOL_SCHEMAS, _without_network_details

class SnapshotToolkit(NereusToolkit):
    def __init__(self, snapshot_dir):
        super().__init__(snapshot_dir=snapshot_dir)
    def execute(self, operation, variables=None, force_refresh=False):
        names={"HelmQuery":"helm.json","ReportsPageQuery":"reports.json","EngineeringQuery":"engineering.json"}
        if operation in names:
            row=json.loads((self.snapshot_dir/names[operation]).read_text())
            return {"ok":True,"data":row["data"],"evidence_mode":"test_snapshot","source_url":self.graphql_url}
        if operation.startswith("PowerCurrentChart"):
            return {"ok":True,"data":{"statistics":{"history":[{"date":"2026-09-17","current":1.0},{"date":"2026-09-18","current":2.0},{"date":"2026-09-19","current":1.5}]}},"evidence_mode":"test_snapshot","source_url":self.graphql_url}
        raise AssertionError(operation)

class NereusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_root=Path(__file__).resolve().parent
        cls.snapshots=source_root/"snapshots"
        if not cls.snapshots.exists(): cls.snapshots=(source_root/"../../data/Nereus/graphrag/snapshots").resolve()
        cls.toolkit=SnapshotToolkit(cls.snapshots)
    def test_has_ten_tools(self): self.assertEqual(len(TOOL_SCHEMAS),10)
    def test_inventory_is_rca_only(self):
        result=self.toolkit.inventory(); self.assertEqual(result["instrument_count"],126); self.assertEqual(result["node_count"],28); self.assertNotIn("ipAddress",json.dumps(result))
    def test_private_network_details_are_removed_recursively(self):
        value={"ipAddress":"10.0.0.8","message":"moved from 192.168.1.2 to 10.31.3.195","public":"https://nereus.ooirsn.uw.edu/"}
        cleaned=_without_network_details(value); rendered=json.dumps(cleaned)
        self.assertNotIn("ipAddress",rendered); self.assertNotIn("192.168.1.2",rendered); self.assertNotIn("10.31.3.195",rendered)
        self.assertIn("[REDACTED PRIVATE NETWORK ADDRESS]",rendered); self.assertEqual(cleaned["public"],value["public"])
    def test_tool_schemas_do_not_offer_network_detail_switch(self):
        self.assertNotIn("include_network_details",json.dumps(TOOL_SCHEMAS))
    def test_instrument_status(self):
        result=self.toolkit.instrument_status("RS01SLBS-MJ01A-12-VEL3DB101"); self.assertTrue(result["ok"]); self.assertEqual(result["total_matches"],1)
    def test_operational_notes_are_rca_linked(self):
        result=self.toolkit.operational_notes("RS01SLBS",cutoff="2025-01-01T00:00:00Z",limit=500); self.assertTrue(result["ok"]); self.assertTrue(all(all(x.startswith("RS") for x in n["referenceDesignators"]) for n in result["notes"]))
    def test_engineering_is_rca_only(self):
        result=self.toolkit.engineering_telemetry(); self.assertEqual(result["total_matches"],17)
    def test_power_plot_returns_mcp_image(self):
        result=self.toolkit.plot_power_history("instrument","RS01SLBS-MJ01A-12-VEL3DB101"); self.assertTrue(result["ok"]); self.assertEqual(result["points"],3); mcp=tool_result(result); self.assertEqual([x["type"] for x in mcp["content"]],["text","image"])

if __name__=="__main__": unittest.main()
