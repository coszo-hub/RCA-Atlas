import { afterEach, describe, expect, it, vi } from "vitest";
import * as THREE from "three";
import { AuvLod } from "./AuvLod.js";

// A tiny survey: 2-cell tiles (S = 3). L0 has two tiles side by side; L1 cells are 1/4 and L2 cells 1/16 of L0's.
const C0 = 0.002, N = 2, S = N + 1, WEST = -130.1, NORTH = 46.05;
const index = (l1 = [[0, 0]], l2 = [[0, 0]]) => ({
  credit: "test", west: WEST, north: NORTH, cellDeg: C0 / 16, tileCells: N, zOffset: -1000, zScale: 10,
  nx: 2 * N * 16, ny: N * 16,   // the survey is exactly the two L0 tiles
  levels: [
    { level: 0, stride: 16, cellDeg: C0, tilesX: 2, tilesY: 1, tiles: [[0, 0], [0, 1]] },
    { level: 1, stride: 4, cellDeg: C0 / 4, tilesX: 8, tilesY: 4, tiles: l1 },
    { level: 2, stride: 1, cellDeg: C0 / 16, tilesX: 32, tilesY: 16, tiles: l2 },
  ],
});
// Every tile is flat at -1500 m (delta-encoded: the first column carries the value, the rest are 0).
const tileBytes = () => { const d = new Int16Array(S * S); for (let r = 0; r < S; r++) d[r * S] = -5000; return d.buffer; };
const ok = body => ({ ok: true, status: 200, headers: { get: () => "application/octet-stream" }, arrayBuffer: async () => body, json: async () => body });
function serve(ix, { fail = [], hold = {} } = {}) {
  return vi.fn(async url => {
    const u = String(url);
    if (u.endsWith("index.json")) return ok(ix);
    if (fail.some(f => u.endsWith(f))) return { ok: false, status: 404, headers: { get: () => "text/plain" } };
    for (const [f, p] of Object.entries(hold)) if (u.endsWith(f)) await p;
    return ok(tileBytes());
  });
}
const scene = () => ({ children: [], add(m) { this.children.push(m); }, remove(m) { this.children = this.children.filter(x => x !== m); } });
const flush = () => new Promise(r => setTimeout(r, 0));

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("AuvLod", () => {
  it("samples only inside the survey; the padded band past its east and south edges is left to the GMRT grid", async () => {
    vi.stubGlobal("fetch", serve(index()));
    const lod = await AuvLod.create(scene(), {}, () => ({}), "/auv/");
    expect(lod.sample(WEST + 1.5 * C0, NORTH - 1.5 * C0)).toBeCloseTo(-1500, 3);
    // Inside a loaded L0 tile's padded area but east of the survey, and south of it.
    const eastEdge = WEST + 2 * N * C0, southEdge = NORTH - N * C0;
    expect(lod.sample(eastEdge + 0.0001, NORTH - 1.5 * C0)).toBeNull();
    expect(lod.sample(WEST + 1.5 * C0, southEdge - 0.0001)).toBeNull();
  });

  it("a failed 16 m tile leaves the summit to the GMRT grid instead of failing the atlas", async () => {
    vi.stubGlobal("fetch", serve(index(), { fail: ["L0/0_1.bin.gz"] }));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const s = scene();
    expect(await AuvLod.create(s, {}, () => ({}), "/auv/")).toBeNull();
    expect(s.children).toEqual([]);
    expect(warn).toHaveBeenCalledWith(expect.stringMatching(/Axial summit detail is unavailable.*HTTP 404/));
  });

  it("the finer-level cache evicts the oldest tiles off screen, keeps shown ones, and disposes what it drops", async () => {
    const l1 = Array.from({ length: 8 }, (_, x) => [0, x]);
    vi.stubGlobal("fetch", serve(index(l1, [])));
    const lod = await AuvLod.create(scene(), {}, () => ({}), "/auv/");
    lod.cacheMax = 3;
    const dispose = vi.spyOn(THREE.BufferGeometry.prototype, "dispose");
    lod._show(1, "0_0", await lod._geometry(1, "0_0"));   // the oldest entry, and on screen
    for (const [y, x] of l1.slice(1)) await lod._geometry(1, `${y}_${x}`);
    expect(lod.cache.size).toBe(3);
    expect(lod.cache.has("1:0_0")).toBe(true);
    expect([...lod.cache.keys()]).toEqual(["1:0_0", "1:0_6", "1:0_7"]);
    expect(dispose).toHaveBeenCalledTimes(5);   // 0_1 … 0_5
    expect([...lod.cache.keys()].some(k => k.startsWith("0:"))).toBe(false);   // the 16 m base is not in the LRU
  });

  it("a tile that fails is not fetched again on every update", async () => {
    const f = serve(index([[0, 0]], []), { fail: ["L1/0_0.bin.gz"] });
    vi.stubGlobal("fetch", f);
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const lod = await AuvLod.create(scene(), {}, () => ({}), "/auv/");
    const [cx, cz] = lod.center(1, "0_0"), tries = () => f.mock.calls.filter(([u]) => String(u).endsWith("L1/0_0.bin.gz")).length;
    lod.update({ x: cx, z: cz }, 10, 1000); await flush(); await flush();
    lod.update({ x: cx, z: cz }, 10, 1300); await flush(); await flush();
    lod.update({ x: cx, z: cz }, 10, 1600); await flush();
    expect(tries()).toBe(1);
    expect(lod.stats().L1).toBe(0);
  });

  it("rejects an HTML answer (Vite's fallback for a missing file)", async () => {
    const f = vi.fn(async url => String(url).endsWith("index.json") ? ok(index())
      : { ok: true, status: 200, headers: { get: () => "text/html" }, arrayBuffer: async () => new ArrayBuffer(18) });
    vi.stubGlobal("fetch", f);
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(await AuvLod.create(scene(), {}, () => ({}), "/auv/")).toBeNull();
  });

  it("a 1 m tile shows only once its 4 m parent is on screen", async () => {
    let release; const parent = new Promise(r => { release = r; });
    vi.stubGlobal("fetch", serve(index(), { hold: { "L1/0_0.bin.gz": parent } }));
    const lod = await AuvLod.create(scene(), {}, () => ({}), "/auv/");
    const [cx, cz] = lod.center(2, "0_0"), t = { x: cx, z: cz };
    lod.update(t, 2, 1000); await flush(); await flush();
    expect(lod.stats()).toMatchObject({ L1: 0, L2: 0 });   // the 1 m tile has loaded; its parent has not
    release(); await flush(); await flush();
    expect(lod.stats().L1).toBe(1);
    lod.update(t, 2, 1300); await flush(); await flush();
    expect(lod.stats().L2).toBe(1);
  });
});
