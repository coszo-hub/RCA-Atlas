import { describe, expect, it, vi } from "vitest";
import { fetchScpr, parseScpr, scprLines } from "./scpr.js";
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
