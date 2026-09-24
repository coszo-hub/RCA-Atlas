import { atlasUrl } from "./paths.js";

export const BUILD_COMMAND = "PYTHONPATH=src .venv/bin/python -m atlas_map_data.build_atlas_bundle";

export class BundleMissingError extends Error {
  constructor() {
    super(`The atlas data bundle is missing. Build it with: ${BUILD_COMMAND}`);
    this.name = "BundleMissingError";
  }
}

// Vite's SPA fallback answers a missing file with 200 text/html, so a 404, a non-JSON
// content type, or a body that fails to parse all mean the file is not there.
async function getJson(fetchImpl, url) {
  const missing = () => (url.endsWith("manifest.json") ? new BundleMissingError()
    : new Error(`The atlas data bundle is incomplete: ${url} is missing or not JSON. Rebuild it with: ${BUILD_COMMAND}`));
  const res = await fetchImpl(url);
  if (!res.ok) {
    if (res.status === 404) throw missing();
    throw new Error(`Could not load ${url} (HTTP ${res.status})`);
  }
  const type = res.headers?.get("content-type");
  if (type != null && !type.includes("json")) throw missing();
  try {
    return await res.json();
  } catch {
    throw missing();
  }
}

export async function loadBundle(fetchImpl = fetch) {
  const manifest = await getJson(fetchImpl, atlasUrl("manifest.json"));
  const [fam, sen, sit, reg, cable, terrainMeta] = await Promise.all(
    ["families", "sensors", "sites", "regions", "cable", "terrain/terrain"].map(n => getJson(fetchImpl, atlasUrl(`${n}.json`))));
  return {
    manifest, families: fam.families, familyByKey: Object.fromEntries(fam.families.map(f => [f.key, f])),
    sensors: sen.sensors, sensorById: Object.fromEntries(sen.sensors.map(s => [s.id, s])), unplaced: sen.unplaced,
    sites: sit.sites, siteById: Object.fromEntries(sit.sites.map(s => [s.id, s])),
    regions: reg.regions, overview: reg.overview, cable, terrainMeta,
  };
}
