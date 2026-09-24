import { describe, expect, it } from "vitest";
import { toX, toZ } from "./geo.js";
import { countBefore, glassWindow, months, quakeArrays, surfaceArrays } from "./subsurface.js";

const eq = { lon0: -130, lat0: 46, scale: 1e-5, day0: "2015-01-22",
  rows: [[0, 0, 1600, 0.5], [1000, -2000, 2400, 9.25], [-500, 500, 1500, 40]] };

describe("subsurface", () => {
  it("places earthquakes at their lon/lat with negative elevation", () => {
    const q = quakeArrays(eq);
    expect(q.positions[3]).toBeCloseTo(toX(-129.99), 4);
    expect(q.positions[5]).toBeCloseTo(toZ(45.98), 4);
    expect(Array.from(q.elev)).toEqual([-1600, -2400, -1500]);
    expect(Array.from(q.day)).toEqual([0.5, 9.25, 40]);
  });

  it("drops the triangles of any cell with a masked corner", () => {
    const p = (lon, lat) => [lon, lat, -2000];
    const s = { rows: 2, cols: 3, points: [p(-130, 46), p(-129.99, 46), null, p(-130, 45.99), p(-129.99, 45.99), p(-129.98, 45.99)] };
    const a = surfaceArrays(s);
    expect(Array.from(a.index)).toEqual([0, 3, 1, 1, 3, 4]);
    expect(a.elev[4]).toBe(-2000);
  });

  it("steps through calendar months from the first day", () => {
    const m = months("2015-01-22", 40);
    expect(m.map(x => x.label)).toEqual(["2015-01", "2015-02", "2015-03"]);
    expect(m[0].end).toBe(10);          // 2015-02-01 is 10 days after 01-22
    expect(m[1].end).toBe(38);
  });

  it("counts sorted days before a time", () => {
    const days = [0.5, 9.25, 40];
    expect(countBefore(days, 0)).toBe(0);
    expect(countBefore(days, 10)).toBe(2);
    expect(countBefore(days, 99)).toBe(3);
  });

  it("opens a glass window that covers the surfaces", () => {
    const data = { earthquakes: eq, surfaces: [{ rows: 1, cols: 2, points: [[-130.05, 46, -3000], [-129.95, 46, -3000]] }] };
    const w = glassWindow(data, 1);
    expect(w.r).toBeGreaterThanOrEqual(Math.abs(toX(-130.05) - w.x) + 1 - 1e-9);
  });
});
