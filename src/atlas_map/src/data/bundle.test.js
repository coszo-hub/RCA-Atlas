import { describe, expect, it } from "vitest";
import { BUILD_COMMAND, BundleMissingError, loadBundle } from "./bundle.js";
import { CABLE, DAS, FAMILIES, MANIFEST, REGIONS, SENSORS, SITES } from "../test/fixtures.js";

const files = {
  "/atlas/manifest.json": MANIFEST, "/atlas/families.json": { families: FAMILIES },
  "/atlas/sensors.json": { sensors: SENSORS, unplaced: [] }, "/atlas/sites.json": { sites: SITES },
  "/atlas/regions.json": REGIONS, "/atlas/cable.json": CABLE, "/atlas/das.json": DAS,
  "/atlas/terrain/terrain.json": { credit: "GMRT, Ryan et al. (2009), CC BY 4.0", grids: {} },
};
const fakeFetch = (overrides = {}) => async url => {
  const body = { ...files, ...overrides }[url];
  return body === undefined ? { ok: false, status: 404 } : { ok: true, status: 200, json: async () => body };
};

describe("loadBundle", () => {
  it("indexes sensors, sites and families", async () => {
    const b = await loadBundle(fakeFetch());
    expect(b.sensorById["base-ctd"].family).toBe("chemistry");
    expect(b.siteById["axial-seamount-base"].sensorIds).toHaveLength(3);
    expect(b.familyByKey.seismic.color).toBe("#d95926");
    expect(b.terrainMeta.credit).toContain("GMRT");
    expect(b.das.layers[0].kind).toBe("multidas");
  });
  it("reports a missing bundle with the build command", async () => {
    await expect(loadBundle(fakeFetch({ "/atlas/manifest.json": undefined }))).rejects.toBeInstanceOf(BundleMissingError);
    await expect(loadBundle(fakeFetch({ "/atlas/manifest.json": undefined }))).rejects.toThrow(/build_atlas_bundle/);
  });
  // Vite's SPA fallback answers a missing file with 200 text/html (index.html).
  const htmlFallback = { ok: true, status: 200, headers: { get: () => "text/html" },
    json: async () => { throw new SyntaxError("Unexpected token '<'"); } };
  const withHtmlFor = target => async url => (url === target ? htmlFallback : fakeFetch()(url));
  it("treats an HTML fallback for the manifest as a missing bundle", async () => {
    await expect(loadBundle(withHtmlFor("/atlas/manifest.json"))).rejects.toBeInstanceOf(BundleMissingError);
  });
  it("reports an HTML fallback for another bundle file as an incomplete bundle", async () => {
    const run = () => loadBundle(withHtmlFor("/atlas/sites.json"));
    await expect(run()).rejects.toThrow(/incomplete: \/atlas\/sites\.json is missing or not JSON/);
    await expect(run()).rejects.toThrow(BUILD_COMMAND);
    await expect(run()).rejects.not.toBeInstanceOf(BundleMissingError);
  });
});
