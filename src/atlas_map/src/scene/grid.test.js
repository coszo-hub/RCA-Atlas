import { describe, expect, it } from "vitest";
import { buildArrays, coarsen, makeGrid, stack } from "./grid.js";

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
  it("coarsens onto the full grid's own cell centres", () => {
    // 5 columns x 3 rows, heights = 10 * row + column, so each sample names its source cell.
    const m = { ncols: 5, nrows: 3, west: -130, south: 45, cellsize: 0.1 };
    const full = makeGrid(m, new Int16Array([0, 1, 2, 3, 4, 10, 11, 12, 13, 14, 20, 21, 22, 23, 24]).buffer);
    const c = coarsen(full, 2);
    expect([c.meta.ncols, c.meta.nrows]).toEqual([3, 2]);
    expect([...c.heights]).toEqual([0, 2, 4, 20, 22, 24]);
    const centre = (g, r, col) => [g.meta.west + (col + 0.5) * g.meta.cellsize, g.meta.south + (g.meta.nrows - r - 0.5) * g.meta.cellsize];
    for (const [r, col] of [[0, 0], [0, 2], [1, 1]]) {
      const [lon, lat] = centre(c, r, col), [flon, flat] = centre(full, r * 2, col * 2);
      expect(lon).toBeCloseTo(flon); expect(lat).toBeCloseTo(flat);
      expect(c.sample(lon, lat)).toBeCloseTo(full.sample(flon, flat));
    }
    expect(coarsen(full, 1)).toBe(full);
  });
  it("builds indexed geometry with gradients", () => {
    const a = buildArrays(g, 1);
    expect(a.positions.length).toBe(18);
    expect(a.index.length).toBe(12);
    expect(a.elev[4]).toBe(-2100);
    expect(a.grad[0]).toBeLessThan(0);   // elevation falls to the east along row 0
  });
});
