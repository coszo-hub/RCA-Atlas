import { describe, expect, it } from "vitest";
import { buildArrays, makeGrid, stack } from "./grid.js";

// 3×2 grid, row 0 = north; same numbers as plan 1's tiny.asc fixture.
const meta = { ncols: 3, nrows: 2, west: -130, south: 45, cellsize: 0.1 };
const buf = new Int16Array([-1000, -1100, -1200, -2000, -2100, -3000]).buffer;

describe("grid", () => {
  const g = makeGrid(meta, buf);
  it("samples bilinearly with row 0 north", () => {
    expect(g.sample(-129.95, 45.15)).toBeCloseTo(-1000);
    expect(g.sample(-129.9, 45.15)).toBeCloseTo(-1050);
    expect(g.sample(-131, 45.1)).toBeNull();
  });
  it("stack falls back", () => {
    const elev = stack([g]);
    expect(elev(-129.95, 45.15)).toBeCloseTo(-1000);
    expect(elev(-140, 45)).toBe(-2500);
  });
  it("builds indexed geometry with gradients", () => {
    const a = buildArrays(g, 1);
    expect(a.positions.length).toBe(18);
    expect(a.index.length).toBe(12);
    expect(a.elev[4]).toBe(-2100);
    expect(a.grad[0]).toBeLessThan(0);   // elevation falls to the east along row 0
  });
});
