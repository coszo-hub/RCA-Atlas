import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from axial_agent_tools import AxialToolkit, TOOL_SCHEMAS, parse_focal_csv, parse_hypo71, parse_ph2dt
from mcp_server import tool_result


HYPO = """yyyymmdd HHMMSSS.SS Lat(D M) Lon(D M) Depth MW NWR GAP DMIN RMS ERH ERZ ID PMom SMom
20260918 2359 60.00 45 60.00 129 60.00 1.25 0.13 12 246 0.9 0.04 1.1 0.9 571855 2.1e+18 NaN
20260918 1200 00.00 45 56.00 130 1.00 0.50 -0.20 8 180 1.2 0.03 0.5 0.6 571856 1e+17 2e+17
"""

PH2DT = """# 2026 9 18 0 4 13.753 45.94014 -130.02077 1.125 0.1 1.088 0.947 0.041 571855
 AXCC1 0.512 0.75 P
 AXCC1 0.982 0.25 S
"""

FOCAL = """EventID,OriginTime,Lat,Lon,DepthKm,Mw,Strike,Dip,Rake,FaultType,nAnalogs,dPo,dLocKm,Po_AS1,Po_AS2,Po_CC1,Po_EC1,Po_EC2,Po_EC3,Po_ID1
1,2026-03-22T00:00:00,45.9,-130.0,1.0,NaN,90,45,-90,N,6,.4,2,1,1,1,1,1,1,1
2,2026-03-23T00:00:00,45.9,-130.0,1.0,0.2,90,45,-90,N,A,6,.4,2,1,1,1,1,1,1,1
2,2026-03-23T00:00:00,45.9,-130.0,1.0,0.2,90,45,-90,N,A,6,.4,2,1,1,1,1,1,1,1
"""


class FakeToolkit(AxialToolkit):
    def __init__(self, db_path):
        super().__init__(db_path=db_path, now_fn=lambda: datetime(2026,9,19,12,tzinfo=timezone.utc))
    def _fetch(self, url, binary=False, force_refresh=False):
        if "hypo71_20260918" in url: return HYPO.encode() if binary else HYPO
        if "ph2dtInputCatalog_20260918" in url: return PH2DT.encode() if binary else PH2DT
        if url.endswith(".jpg"): return b"\xff\xd8test"
        if url.endswith(".png"): return b"\x89PNGtest"
        if "/events/FM_" in url: return "<html><body><h2>Focal Mechanism</h2><p>fixture</p></body></html>"
        raise OSError("fixture has no URL")


class AxialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Path(self.tmp.name)/"events.sqlite"
        with sqlite3.connect(self.db) as db:
            db.executescript("CREATE TABLE events(record_key TEXT,event_id TEXT,origin_time_utc TEXT,event_date_utc TEXT,latitude REAL,longitude REAL,depth_km REAL,magnitude_mw REAL,weighted_readings INTEGER,azimuthal_gap_deg REAL,nearest_station_km REAL,rms_seconds REAL,horizontal_error_km REAL,vertical_error_km REAL,p_moment REAL,s_moment REAL,site_id TEXT,source_url TEXT,source_line INTEGER); CREATE TABLE focal_mechanisms(event_id TEXT,origin_time_utc TEXT);")
            db.execute("INSERT INTO focal_mechanisms VALUES (?,?)",("571855","2026-09-18T00:04:13Z"))
        self.tool=FakeToolkit(self.db)
    def tearDown(self): self.tmp.cleanup()
    def test_hypo_parser_handles_rollover_and_nan(self):
        rows=parse_hypo71(HYPO,"fixture"); self.assertEqual(len(rows),2); self.assertEqual(rows[0]["origin_time_utc"],"2026-09-19T00:00:00Z"); self.assertAlmostEqual(rows[0]["latitude"],46.0); self.assertAlmostEqual(rows[0]["longitude"],-130.0); self.assertIsNone(rows[0]["s_moment"]); self.assertNotEqual(rows[0]["record_key"],rows[1]["record_key"])
    def test_count_yesterday_is_live_and_row_based(self):
        result=self.tool.count_events("yesterday"); self.assertTrue(result["ok"]); self.assertEqual(result["earthquake_count"],2); self.assertEqual(result["day_utc"],"2026-09-18"); self.assertEqual(result["timezone"],"UTC")
    def test_magnitude_filter(self): self.assertEqual(self.tool.count_events("2026-09-18",min_magnitude=0)["earthquake_count"],1)
    def test_arrival_parser(self):
        result=self.tool.arrivals("2026-09-18","571855"); self.assertEqual(result["total_events"],1); self.assertEqual([x["phase"] for x in result["events"][0]["picks"]],["P","S"])
    def test_focal_schema_drift_and_duplicate(self):
        rows=parse_focal_csv(FOCAL,"fixture"); self.assertEqual(len(rows),2); self.assertIsNone(rows[0]["quality"]); self.assertEqual(rows[1]["quality"],"A"); self.assertIsNone(rows[0]["magnitude_mw"])
    def test_figure_is_mcp_image(self): self.assertEqual([x["type"] for x in tool_result(self.tool.get_figure("caldera_1_day"))["content"]],["text","image"])
    def test_focal_event_image_is_mcp_image(self): self.assertEqual([x["type"] for x in tool_result(self.tool.focal_event_product("571855","waveform"))["content"]],["text","image"])
    def test_monthly_summary_snapshot(self): self.assertEqual(self.tool.monthly_focal_summary("2026-09",source="snapshot")["earthquake_focal_mechanism_count"],1)
    def test_tool_count(self): self.assertEqual(len(TOOL_SCHEMAS),13)


if __name__ == "__main__": unittest.main()
