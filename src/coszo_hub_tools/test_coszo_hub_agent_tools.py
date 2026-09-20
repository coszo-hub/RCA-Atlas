#!/usr/bin/env python3
from __future__ import annotations

import base64
import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from coszo_hub_agent_tools import CoszoHubToolkit, dispatch


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


class ToolkitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repo = base / "repos"
        self.roots = {}
        for name in ["absolute-seafloor-pressure", "chronfix", "dive-index-hindcast", "sea-water-velocity"]:
            root = base / "outputs" / name
            root.mkdir(parents=True)
            self.roots[name] = root
            (self.repo / name).mkdir(parents=True)
        metrics = self.roots["absolute-seafloor-pressure"] / "RS01SUM1_variability.csv"
        metrics.write_text("date,station,has_data,n_gaps,true_missing,jitter_unstable\n2026-01-01,RS01SUM1-MJ00-00-TEST,True,2,3,False\n", encoding="utf-8")
        fig = self.roots["sea-water-velocity"] / "RS03AXBS-MJ03A-12-VEL3DB301_2026-01-01_variability_4panel.png"
        fig.write_bytes(PNG)
        hours = np.arange(np.datetime64("2024-01-01T00"), np.datetime64("2024-01-01T06"), dtype="datetime64[h]")
        np.save(self.roots["chronfix"] / "hour_times.npy", hours)
        np.save(self.roots["chronfix"] / "delta_t_hourly_clean.npy", np.arange(6, dtype=float))
        (self.roots["chronfix"] / "trigger_periods.csv").write_text("start_index,end_index\n2,3\n", encoding="utf-8")
        gap_dir = self.repo / "absolute-seafloor-pressure" / "PREST-data-collection" / "bin"
        gap_dir.mkdir(parents=True)
        upstream = Path(__file__).resolve().parents[2] / "coszo_hub" / "absolute-seafloor-pressure" / "PREST-data-collection" / "bin" / "gap_algorithms.py"
        if upstream.exists():
            (gap_dir / "gap_algorithms.py").write_bytes(upstream.read_bytes())
        self.toolkit = CoszoHubToolkit(self.repo, base / "index.sqlite", base / "cache", self.roots)

    def tearDown(self): self.temp.cleanup()

    def test_incremental_scan_sees_new_file(self):
        first = self.toolkit.status()
        self.assertEqual(first["repositories"]["absolute-seafloor-pressure"]["file_count"], 1)
        (self.roots["absolute-seafloor-pressure"] / "new.log").write_text("new", encoding="utf-8")
        second = self.toolkit.status()
        self.assertEqual(second["repositories"]["absolute-seafloor-pressure"]["file_count"], 2)

    def test_metric_summary(self):
        result = self.toolkit.metric_summary("absolute-seafloor-pressure", "RS01SUM1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["days_with_corrected_gaps"], 1)
        self.assertEqual(result["total_missing_samples"], 3)

    def test_figure_and_path_guard(self):
        rel = "RS03AXBS-MJ03A-12-VEL3DB301_2026-01-01_variability_4panel.png"
        result = self.toolkit.get_figure("sea-water-velocity", rel)
        self.assertTrue(result["ok"])
        self.assertIn("_mcp_image", result)
        self.assertFalse(self.toolkit.read_output("sea-water-velocity", "../escape")["ok"])

    def test_chronfix_and_dive_calculation(self):
        model = self.toolkit.chronfix_model(["2024-01-01T01:30:00", "2024-01-01T02:30:00"])
        self.assertTrue(model["ok"])
        self.assertAlmostEqual(model["queries"][0]["delta_t_seconds"], 1.5)
        self.assertIsNone(model["queries"][1]["delta_t_seconds"])
        self.assertEqual(model["trigger_periods"][0]["start_time_utc"], "2024-01-01T02:00:00Z")
        self.assertEqual(model["trigger_periods"][0]["end_time_utc"], "2024-01-01T03:00:00Z")
        self.assertEqual(len(model["bundle_fingerprint_sha256"]), 64)
        corrected = self.toolkit.hys14_correct_times(["2024-01-01T01:30:00Z"], "OO.HYS14.OBS", channel="BHZ")
        self.assertTrue(corrected["ok"])
        self.assertEqual(corrected["corrections"][0]["corrected_true_utc"], "2024-01-01T01:29:58.500000Z")
        self.assertEqual(corrected["target"]["requested_channel"], "BHZ")
        wrong = self.toolkit.hys14_correct_times(["2024-01-01T01:30:00Z"], "OO.HYS14.PREST")
        self.assertFalse(wrong["ok"])
        dive = self.toolkit.compute_dive_index(2, wind_speed_mps=10)
        self.assertAlmostEqual(dive["dive_index"], 38.87688984)

    def test_hys14_routing_scopes_one_instrument(self):
        seismic = self.toolkit.question_context("What happened in the HYS14 seismic waveform at 2024-01-01T01:30:00Z?")
        self.assertEqual(seismic["hys14_clock_context"]["applicability"], "affected_instrument_likely; MHZ-derived correction applies to all channels sharing the HYS14 OBS clock")
        self.assertEqual(len(seismic["hys14_clock_context"]["timestamp_corrections"]), 1)
        pressure = self.toolkit.question_context("What did the HYS14 PREST pressure show at 2024-01-01T01:30:00Z?")
        self.assertEqual(pressure["hys14_clock_context"]["applicability"], "different_instrument")
        self.assertEqual(pressure["hys14_clock_context"]["timestamp_corrections"], [])
        generic = self.toolkit.question_context("What was happening at HYS14 on 2024-01-01?")
        self.assertEqual(generic["hys14_clock_context"]["applicability"], "instrument_unspecified")
        self.assertIn("day_context", generic["hys14_clock_context"])

    def test_chronfix_bundle_is_reopened_after_update(self):
        first = self.toolkit.chronfix_model(["2024-01-01T01:00:00Z"], refresh=False)
        fingerprint = first["bundle_fingerprint_sha256"]
        delta_path = self.roots["chronfix"] / "delta_t_hourly_clean.npy"
        values = np.load(delta_path)
        np.save(delta_path, values + 10.0)
        second = self.toolkit.chronfix_model(["2024-01-01T01:00:00Z"], refresh=False)
        self.assertNotEqual(fingerprint, second["bundle_fingerprint_sha256"])
        self.assertAlmostEqual(second["queries"][0]["delta_t_seconds"], 11.0)
        refresh = self.toolkit.refresh_hys14_correction()
        self.assertEqual(refresh["mode"], "local_snapshot")

    def test_gap_detector_and_filtered_output_list(self):
        timestamps = [float(i) for i in range(101) if i != 50]
        result = self.toolkit.detect_pressure_gaps(timestamps, 1.0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["gap_indices"], (49,))
        self.assertEqual(result["diagnostics"]["true_missing"], 1)
        listed = self.toolkit.list_outputs("absolute-seafloor-pressure", station="RS01SUM1")
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["total_matches"], 1)

    def test_dispatch_unknown(self):
        self.assertFalse(dispatch(self.toolkit, "missing", {})["ok"])


if __name__ == "__main__": unittest.main()
