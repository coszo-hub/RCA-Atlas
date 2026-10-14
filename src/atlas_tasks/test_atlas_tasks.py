"""Unit tests for the sandbox task tools (run: PYTHONPATH=src python -m pytest src/atlas_tasks)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from atlas_eval import synth
from atlas_tasks import dvv, earthquakes, gaps, pressure, router, timing
from atlas_tasks.tools import Sandbox, dispatch

FIXTURES = Path(__file__).resolve().parents[1] / "atlas_worker" / "test" / "fixtures"


def test_cross_correlation_sign_convention():
    rng = np.random.default_rng(0)
    a = rng.standard_normal(4000)
    b = np.roll(a, 12)                       # b lags a by 12 samples
    cc = timing.cross_correlate(a, b, fs=8.0, maxlag_s=5.0)
    assert timing.lag_axis(8.0, 5.0)[np.argmax(cc)] == pytest.approx(1.5)


def test_clock_track_recovers_a_jump():
    truth = synth.clock_error_series("jump", 72, np.random.default_rng(0), jump_s=2.5, jump_hour=30)
    a, b = synth.station_pair(days=3, fs=8.0, travel_s=3.0, snr=0.5, clock_dt_hourly=truth, seed=1)
    res = timing.clock_track(a, b, 8.0)
    jumps = res["diagnosis"].jumps
    assert res["diagnosis"].kind == "jump"
    assert len(jumps) == 1 and abs(jumps[0]["time_s"] / 3600 - 30) <= 1
    assert jumps[0]["size_s"] == pytest.approx(-2.5, abs=0.15)


def test_correct_times_subtracts_delta_t():
    corrected = timing.correct_times(np.array([1800.0]), np.array([0.0, 3600.0]), np.array([1.0, 3.0]))
    assert corrected[0] == pytest.approx(1798.0)


@pytest.mark.parametrize("method", ["stretching", "mwcs", "dtw"])
def test_dvv_methods_recover_known_change(method):
    lags, ref = synth.synthetic_ccf(fs=10.0, maxlag_s=60.0, seed=3)
    cur = synth.noisy(synth.stretch_ccf(lags, ref, 0.003), 20, np.random.default_rng(4))
    kw = {"tmin": 10.0, "tmax": 50.0, **({"fmin": 0.2, "fmax": 2.0} if method == "mwcs" else {})}
    assert dvv.measure(ref, cur, lags, method, **kw).dvv == pytest.approx(0.003, abs=3e-4)


def test_a0a_calibration_removes_drift():
    r = synth.pressure_record(days=120, dt_s=30, seed=2, rate_kpa_per_yr=3.0, calibration="a0a")
    out = pressure.calibrate(r["t_s"], r["reading_kpa"], kind="a0a", reference_kpa=101.325)
    assert len(out["windows"]) == len(r["calibrations"])
    assert out["model"].params["rate_kpa_per_yr"] == pytest.approx(3.0, abs=0.1)
    assert np.sqrt(np.nanmean((out["corrected_kpa"] - r["true_kpa"]) ** 2)) < 0.05


def test_scpr_ignores_tidal_slack_at_the_reference_level():
    r = synth.pressure_record(days=180, dt_s=15, seed=2, rate_kpa_per_yr=3.0, calibration="scpr", cal_reference_kpa=15302.0)
    found = pressure.find_calibrations(r["t_s"], r["reading_kpa"], kind="scpr", reference_kpa=15302.0)
    starts = {round(c["start_s"] / 86400) for c in r["calibrations"]}
    assert found and all(round(w.start_s / 86400) in starts for w in found)


def test_linear_drift_estimate_and_known_correction():
    r = synth.pressure_record(days=90, dt_s=60, seed=5, rate_kpa_per_yr=-2.0)
    est = pressure.estimate_linear_drift(r["t_s"], r["reading_kpa"])
    assert est["rate_kpa_per_yr"] == pytest.approx(-2.0, abs=0.05)
    fixed = pressure.apply_known_drift(r["t_s"], r["reading_kpa"], rate_kpa_per_yr=-2.0)
    assert np.std(fixed - r["true_kpa"]) < 0.02


def test_diagnose_separates_gap_and_timing_families():
    s = synth.faulty_series(n=3000, period_s=1.0, seed=1, faults=[
        {"kind": "gap", "start": 500, "length": 20}, {"kind": "duplicate", "start": 1500, "length": 2},
        {"kind": "backstep", "start": 2200, "size_s": 3.0}])
    out = gaps.diagnose_series(s["t_s"], s["x"])
    assert out["summary"] == {"backstep": 1, "duplicate": 1, "gap": 1}
    assert out["families"] == ["data_gap", "timing_error"]


def test_fill_gaps_restores_the_grid():
    t = np.array([0.0, 1, 2, 5, 6])
    grid, x = gaps.fill_gaps(t, np.arange(5.0))
    assert grid.tolist() == [0, 1, 2, 3, 4, 5, 6] and np.isnan(x[3:5]).all()


def test_hypo71_counts_match_the_worker_fixtures():
    events, missing = earthquakes.load_events("2026-09-23", "2026-09-25", earthquakes.directory_loader(FIXTURES))
    hist = earthquakes.histogram(events, by="day", start="2026-09-23", end="2026-09-25")
    assert hist["counts"] == [71, 98, 4] and not missing
    assert any(e["mag"] < 0 for e in events)


def test_quake_request_parsing():
    today = date(2026, 9, 25)
    assert earthquakes.parse_quake_request("How many earthquakes at Axial between 2026-09-23 and 2026-09-24?", today=today) == \
        {"start": "2026-09-23", "end": "2026-09-24", "min_mag": None}
    assert earthquakes.parse_quake_request("How many Axial earthquakes yesterday above magnitude 1?", today=today) == \
        {"start": "2026-09-24", "end": "2026-09-24", "min_mag": 1.0}
    assert earthquakes.parse_quake_request("How many earthquakes has Axial had?", today=today) is None


def test_router_names_the_task_and_its_tools():
    r = router.route("Compute peak lags for the HYS12-HYS14 pair to correct timing errors")
    assert r.task == "timing_correction" and "atlas_clock_track" in r.handler["tools"]
    assert router.route("What is the Regional Cabled Array?").task == "general_research"


def test_dispatch_refuses_paths_outside_the_sandbox(tmp_path):
    out = dispatch(Sandbox(tmp_path), "atlas_diagnose_series", {"path": "../../etc/passwd"})
    assert out["ok"] is False and out["error"]["type"] == "PermissionError"


def test_dispatch_quake_histogram_from_cache(tmp_path):
    sb = Sandbox(tmp_path, quake_loader=earthquakes.directory_loader(FIXTURES))
    out = dispatch(sb, "atlas_quake_histogram", {"start": "2026-09-23", "end": "2026-09-24", "min_magnitude": 1.0, "plot": "q.png"})
    assert out["ok"] and out["count"] == sum(1 for e in earthquakes.load_events("2026-09-23", "2026-09-24",
                                                                                 earthquakes.directory_loader(FIXTURES))[0] if e["mag"] >= 1.0)
    assert (tmp_path / "q.png").exists()


def test_mcp_server_lists_and_calls_tools(tmp_path):
    server = Path(__file__).with_name("mcp_server.py")
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "atlas_route_question",
                                                                         "arguments": {"question": "Compute dv/v with stretching"}}}]
    proc = subprocess.run([sys.executable, str(server)], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                          capture_output=True, text=True, env={"ATLAS_SANDBOX_DIR": str(tmp_path)}, timeout=60)
    replies = [json.loads(line) for line in proc.stdout.splitlines()]
    assert len(replies[1]["result"]["tools"]) == 11
    assert json.loads(replies[2]["result"]["content"][0]["text"])["task"] == "dvv_monitoring"


def test_tool_results_are_plain_json(tmp_path):
    s = synth.faulty_series(n=3000, period_s=1.0, seed=6001, faults=[
        {"kind": "duplicate", "start": 900, "length": 3}, {"kind": "zero_fill", "start": 2200, "length": 80}])
    np.savez(tmp_path / "s.npz", t_s=s["t_s"], x=s["x"])
    out = dispatch(Sandbox(tmp_path), "atlas_diagnose_series", {"path": "s.npz"})
    json.dumps(out, allow_nan=False)
    assert out["ok"] and out["summary"] == {"duplicate": 1, "zero_fill": 1}


# ---- regressions from the pre-landing review ----

def test_outputs_cannot_escape_the_sandbox(tmp_path):
    box = tmp_path / "box"
    box.mkdir()
    outside = tmp_path / "victim.npz"
    (box / "evil.npz").symlink_to(outside)
    sb = Sandbox(box)
    for name in ("evil", "evil.npz", "../x", "sub/../../x", "/tmp/x"):
        with pytest.raises(PermissionError):
            sb.save(name, a=[1])
    assert sb.save(".", a=[1]) == "..npz"           # suffix added first, so "." stays inside
    assert not outside.exists() and not (tmp_path / "box.npz").exists()
    assert sb.save("filled.json", a=[1]) == "filled.json.npz"      # the returned name is the real file


def test_sandbox_requires_a_directory(monkeypatch):
    monkeypatch.delenv("ATLAS_SANDBOX_DIR", raising=False)
    with pytest.raises(ValueError):
        Sandbox()


def test_mcp_stdout_carries_only_json(tmp_path):
    t = np.arange(100.0)
    t[50] = np.nan
    np.savez(tmp_path / "s.npz", t_s=t, x=np.sin(t))
    server = Path(__file__).with_name("mcp_server.py")
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "atlas_diagnose_series", "arguments": {"path": "s.npz"}}}]
    proc = subprocess.run([sys.executable, str(server)], input="\n\n".join(json.dumps(m) for m in msgs) + "\n",
                          capture_output=True, text=True, env={"ATLAS_SANDBOX_DIR": str(tmp_path)}, timeout=60)
    replies = [json.loads(line) for line in proc.stdout.splitlines()]      # every line parses
    assert [r["id"] for r in replies] == [1, 2, 3]
    assert replies[0]["result"]["protocolVersion"] == "2024-11-05" and replies[1]["result"] == {}


def test_one_bad_timestamp_does_not_wreck_the_series():
    t = np.arange(1000.0)
    x = np.sin(t / 30)
    glitch = t.copy()
    glitch[500] = 1e6
    grid, filled = gaps.fill_gaps(glitch, x)
    assert len(grid) == 1000 and np.isnan(filled).sum() == 1
    nan_t = t.copy()
    nan_t[300] = np.nan
    assert gaps.diagnose_series(nan_t, x)["summary"]["bad_timestamp"] == 1
    with pytest.raises(ValueError):
        gaps.fill_gaps(np.r_[0.0, 1.0, 2.0, 1e12], np.zeros(4), period_s=1.0)


def test_quantized_plateaus_are_not_faults():
    q = np.round(np.sin(np.arange(20000) / 300) * 20)
    assert gaps.diagnose_series(np.arange(20000.0), q)["findings"] == []
    q[5000:7000] = q[5000]
    assert gaps.diagnose_series(np.arange(20000.0), q)["summary"] == {"flatline": 1}


@pytest.mark.parametrize("method", ["stretching", "dtw"])
def test_dvv_refuses_an_empty_coda_window(method):
    lags, ref = synth.synthetic_ccf(fs=10.0, maxlag_s=8.0, seed=3)
    with pytest.raises(ValueError):
        dvv.measure(ref, ref, lags, method, tmin=10.0, tmax=50.0)


def test_unreachable_catalog_stops_early():
    calls = []

    def dead(day):
        calls.append(day)
        raise OSError("unreachable")
    events, missing = earthquakes.load_events("2026-01-01", "2026-12-31", dead, workers=1)
    assert not events and len(missing) == 365 and len(calls) <= 4


def test_quake_request_year_rollover_and_bad_dates():
    jan = date(2026, 1, 10)
    assert earthquakes.parse_quake_request("How many quakes at Axial since Dec 20?", today=jan)["start"] == "2025-12-20"
    assert earthquakes.parse_quake_request("histogram by magnitude 2026-01-01 to 2026-01-05", today=jan)["min_mag"] is None
    assert earthquakes.parse_quake_request("Axial quakes on 2026-02-30", today=jan) is None
