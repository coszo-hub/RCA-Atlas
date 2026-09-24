import { describe, expect, it } from "vitest";
import { KX, KZ, toX, toZ } from "./geo.js";
import { coverage, decode, tileArrays, wanted } from "./auvTiles.js";

describe("decode", () => {
  it("cumulative sum per row, scaled and offset", () => {
    const d = new Int16Array([-5000, 10, -20, -6000, 0, 5, -7000, 1, 1]);   // 3x3
    const m = decode(d, 3, 10, -1000);
    expect(Array.from(m)).toEqual([-1500, -1499, -1501, -1600, -1600, -1599.5, -1700, -1699.9, -1699.8].map(v => Math.fround(v)));
  });
});

describe("tileArrays", () => {
  it("grid plus a skirt ring with drop", () => {
    const S = 3, h = new Float32Array(9).fill(-1500);
    const a = tileArrays(h, S, -130, 46, 0.001);
    expect(a.elev.length).toBe(9 + 4 * (S - 1));
    expect(Array.from(a.drop.slice(0, 9)).every(v => v === 0)).toBe(true);
    expect(Array.from(a.drop.slice(9)).every(v => v === 25)).toBe(true);
    expect(a.index.length).toBe((S - 1) * (S - 1) * 6 + 4 * (S - 1) * 6);
    expect(a.positions[2]).toBeLessThan(a.positions[3 * 3 + 2]);   // row 0 is north (smaller z)
  });
});

describe("wanted", () => {
  const levels = [
    { have: new Set(["0_0"]) },
    { have: new Set(["0_0", "0_5"]) },
    { have: new Set(["0_1", "3_3"]) },
  ];
  const centers = { 1: { "0_0": [0, 0], "0_5": [10, 0] }, 2: { "0_1": [0.2, 0], "3_3": [0.5, 0.5] } };
  const tileCenter = (k, key) => centers[k][key];
  it("far away: only the 16 m level", () => {
    const w = wanted(levels, { x: 0, z: 0 }, 60, tileCenter);
    expect([...w[1]]).toEqual([]); expect([...w[2]]).toEqual([]);
  });
  it("mid range: 4 m tiles near the target", () => {
    const w = wanted(levels, { x: 0, z: 0 }, 10, tileCenter);
    expect([...w[1]]).toEqual(["0_0"]); expect([...w[2]]).toEqual([]);
  });
  it("close: 1 m tiles near the target pull in their 4 m parent", () => {
    const w = wanted(levels, { x: 0, z: 0 }, 2, tileCenter);
    expect([...w[2]].sort()).toEqual(["0_1"]);
    expect(w[1].has("0_0")).toBe(true);
  });
});

describe("coverage", () => {
  // Vertices sit at cell centers, so a level's meshes start half a cell in from the survey's west and north
  // edges. The rectangle a coarser level (or the GMRT patch) discards must match that, or a crack shows.
  it("matches the extent of the tile meshes", () => {
    const S = 5, cellDeg = 0.001, tileDeg = cellDeg * (S - 1), west = -130.1, north = 46.05, h = new Float32Array(S * S);
    const [lon0, lat0, lon1, lat1] = coverage(west, north, cellDeg, tileDeg, 3, 2);
    const first = tileArrays(h, S, west, north, cellDeg);
    const last = tileArrays(h, S, west + 2 * tileDeg, north - 1 * tileDeg, cellDeg);
    // Float32 positions; to 0.5 m, where half a cell here is 39 m
    expect(toX(lon0)).toBeCloseTo(first.positions[0], 3);
    expect(toZ(lat0)).toBeCloseTo(first.positions[2], 3);
    expect(toX(lon1)).toBeCloseTo(last.positions[(S * S - 1) * 3], 3);
    expect(toZ(lat1)).toBeCloseTo(last.positions[(S * S - 1) * 3 + 2], 3);
  });
});

describe("tileArrays gradients", () => {
  it("a plane has the same slope at the tile's edges as inside (one-sided differences use their real span)", () => {
    const S = 4, cellDeg = 0.001, h = new Float32Array(S * S);
    for (let r = 0; r < S; r++) for (let c = 0; c < S; c++) h[r * S + c] = 10 * c + 3 * r;
    const a = tileArrays(h, S, -130, 46, cellDeg), dx = cellDeg * KX, dz = cellDeg * KZ;
    for (let i = 0; i < S * S; i++) {
      expect(a.grad[i * 2]).toBeCloseTo(10 / dx, 3);
      expect(a.grad[i * 2 + 1]).toBeCloseTo(3 / dz, 3);
    }
  });
});
