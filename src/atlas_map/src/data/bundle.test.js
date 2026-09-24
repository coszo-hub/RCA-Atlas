import { describe, expect, it } from "vitest";
import { BundleMissingError, loadBundle } from "./bundle.js";
import { CABLE, FAMILIES, MANIFEST, REGIONS, SENSORS, SITES } from "../test/fixtures.js";

const files = {
  "/atlas/manifest.json": MANIFEST, "/atlas/families.json": { families: FAMILIES },
  "/atlas/sensors.json": { sensors: SENSORS, unplaced: [] }, "/atlas/sites.json": { sites: SITES },
  "/atlas/regions.json": REGIONS, "/atlas/cable.json": CABLE,
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
  });
  it("reports a missing bundle with the build command", async () => {
    await expect(loadBundle(fakeFetch({ "/atlas/manifest.json": undefined }))).rejects.toBeInstanceOf(BundleMissingError);
    await expect(loadBundle(fakeFetch({ "/atlas/manifest.json": undefined }))).rejects.toThrow(/build_atlas_bundle/);
  });
});
