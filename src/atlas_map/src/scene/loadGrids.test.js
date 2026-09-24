import { describe, expect, it } from "vitest";
import { BUILD_COMMAND } from "../data/bundle.js";
import { loadGrids } from "./grid.js";

const meta = { grids: { tiny: { ncols: 3, nrows: 2, west: -130, south: 45, cellsize: 0.1 } } };
const bin = new Int16Array([-1000, -1100, -1200, -2000, -2100, -3000]).buffer;
const res = ({ ok = true, status = 200, type = "application/octet-stream", body = bin } = {}) =>
  ({ ok, status, headers: { get: () => type }, arrayBuffer: async () => body });
const fakeFetch = r => async url => { fakeFetch.urls.push(url); return r; };
fakeFetch.urls = [];

describe("loadGrids", () => {
  it("loads each grid from /atlas/terrain/<name>.bin", async () => {
    const grids = await loadGrids(meta, fakeFetch(res()));
    expect(fakeFetch.urls).toContain("/atlas/terrain/tiny.bin");
    expect(grids.tiny.sample(-129.95, 45.15)).toBeCloseTo(-1000);
  });
  it("names the build command when a grid is missing (404)", async () => {
    const p = loadGrids(meta, fakeFetch(res({ ok: false, status: 404 })));
    await expect(p).rejects.toThrow(/\/atlas\/terrain\/tiny\.bin is missing/);
    await expect(p).rejects.toThrow(BUILD_COMMAND);
  });
  it("reports other HTTP failures", async () => {
    await expect(loadGrids(meta, fakeFetch(res({ ok: false, status: 500 })))).rejects.toThrow(/tiny\.bin \(HTTP 500\)/);
  });
  it("treats Vite's HTML fallback as a missing grid", async () => {
    const p = loadGrids(meta, fakeFetch(res({ type: "text/html" })));
    await expect(p).rejects.toThrow(/tiny\.bin is missing/);
    await expect(p).rejects.toThrow(BUILD_COMMAND);
  });
  it("rejects a grid whose size does not match the metadata", async () => {
    const p = loadGrids(meta, fakeFetch(res({ body: new ArrayBuffer(10) })));
    await expect(p).rejects.toThrow(/tiny\.bin has 10 bytes; expected 12/);
    await expect(p).rejects.toThrow(BUILD_COMMAND);
  });
});
