import { describe, expect, it, vi } from "vitest";
import { fetchScpr, godin, parseScpr, scprLines } from "./scpr.js";
import { SCPR_CSV } from "../../test/fixtures/scpr.js";

describe("parseScpr", () => {
  it("reads the times, both gauges, the regeneration time and the provisional-drift date", () => {
    const d = parseScpr(SCPR_CSV);
    expect(d.t).toEqual([Date.parse("2018-07-06T08:00:00Z"), Date.parse("2025-12-01T00:00:00Z"),
      Date.parse("2026-11-13T22:00:00Z"), Date.parse("2026-11-13T23:00:00Z")]);
    expect(d.cols.paro1_raw_pa[0]).toBe(15546892.6);
    expect(d.cols.paro2_uplift_m).toEqual([null, 0.598, null, null]);
    expect(d.generated).toBe("2026-11-14T00:50Z");
    expect(d.provisionalAfter).toBe("2026-02-05");
  });
  it("names a missing column instead of plotting the wrong one", () => {
    expect(parseScpr("time_utc,paro1_raw_pa\n2026-01-01T00:00:00Z,1\n").error).toBe(
      "the file has no paro1_uplift_m, paro2_uplift_m, paro1_corr_pa, paro2_corr_pa, paro2_raw_pa columns");
    expect(parseScpr("# only notes\n").error).toBe("the file has no rows");
  });
});

describe("scprLines", () => {
  const d = parseScpr(SCPR_CSV);
  it("All keeps every row; pressures are in kPa", () => {
    const l = scprLines(d, "raw", "All");
    expect(l.count).toBe(4);
    expect(l.series.map(s => s.label)).toEqual(["PARO1", "PARO2"]);
    expect(l.series[0].values[0]).toBeCloseTo(15546.8926, 4);
    expect(l.measure.unit).toBe("kPa");
  });
  it("a range ends at the newest row, and says when it has no values", () => {
    const year = scprLines(d, "uplift", "1y");
    expect(year.x[0]).toBe(Date.parse("2025-12-01T00:00:00Z"));
    expect(year.readings).toBe(true);
    const month = scprLines(d, "uplift", "30d");
    expect(month.count).toBe(2);
    expect(month.readings).toBe(false);
    expect(month.lastValueAt).toBe(Date.parse("2025-12-01T00:00:00Z"));   // uplift stops before the raw pressure does
    expect(scprLines(d, "raw", "30d").lastValueAt).toBe(Date.parse("2026-11-13T23:00:00Z"));
  });
});

describe("fetchScpr", () => {
  it("reports GitHub failures as GitHub's, not the live gateway's", async () => {
    const down = await fetchScpr("u", { fetchImpl: vi.fn(async () => ({ ok: false, status: 404 })) });
    expect(down).toMatchObject({ ok: false, source: "GitHub", message: "the SCPR file returned HTTP 404" });
    const offline = await fetchScpr("u", { fetchImpl: vi.fn(async () => { throw new TypeError("Failed to fetch"); }) });
    expect(offline).toMatchObject({ ok: false, kind: "upstream", source: "GitHub" });
  });
});

describe("godin", () => {
  const H = 3600e3, t0 = Date.parse("2026-01-01T00:00:00Z");
  // Ten days of hourly pressure: a slow rise plus M2 and K1 tides of a few kPa.
  const hours = Array.from({ length: 240 }, (_, i) => i);
  const t = hours.map(i => t0 + i * H);
  const trend = i => 1.55e7 + 10 * i;
  const tide = i => 3000 * Math.cos(2 * Math.PI * i / 12.4206) + 1500 * Math.cos(2 * Math.PI * i / 23.9345);
  it("removes diurnal and semidiurnal tides and keeps the trend", () => {
    const y = godin(t, hours.map(i => trend(i) + tide(i)));
    const kept = hours.filter(i => y[i] != null);
    expect(kept[0]).toBeGreaterThan(24);   // a day or more lost at each end
    expect(240 - 1 - kept.at(-1)).toBeGreaterThan(24);
    for (const i of kept) expect(Math.abs(y[i] - trend(i))).toBeLessThan(30);   // of a 3 kPa tide
  });
  it("puts missing hours back on the grid and leaves out what a gap leaves too thin", () => {
    const gone = new Set(hours.filter(i => i >= 100 && i < 110));   // ten hours with no row
    const y = godin(t.filter((_, i) => !gone.has(i)), hours.filter(i => !gone.has(i)).map(i => trend(i) + tide(i)));
    const at = Object.fromEntries(hours.filter(i => !gone.has(i)).map((i, k) => [i, y[k]]));
    expect(at[99]).toBeNull();
    expect(Math.abs(at[60] - trend(60))).toBeLessThan(30);
    expect(Math.abs(at[170] - trend(170))).toBeLessThan(30);
  });
  it("detided pressure ends a day or more before the newest row", () => {
    const d = { t, cols: { paro1_raw_pa: hours.map(i => trend(i) + tide(i)), paro2_raw_pa: hours.map(() => null) } };
    const l = scprLines(d, "raw", "All", true);
    expect(l.readings).toBe(true);
    expect(t.at(-1) - l.lastValueAt).toBeGreaterThan(24 * H);
    expect(scprLines(d, "raw", "All", false).lastValueAt).toBe(t.at(-1));
  });
});
