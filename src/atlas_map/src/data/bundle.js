export class BundleMissingError extends Error {
  constructor() {
    super("The atlas data bundle is missing. Build it with: PYTHONPATH=src .venv/bin/python -m atlas_map_data.build_atlas_bundle");
    this.name = "BundleMissingError";
  }
}

async function getJson(fetchImpl, url) {
  const res = await fetchImpl(url);
  if (!res.ok) {
    if (url.endsWith("manifest.json") && res.status === 404) throw new BundleMissingError();
    throw new Error(`Could not load ${url} (HTTP ${res.status})`);
  }
  return res.json();
}

export async function loadBundle(fetchImpl = fetch) {
  const manifest = await getJson(fetchImpl, "/atlas/manifest.json");
  const [fam, sen, sit, reg, cable, terrainMeta] = await Promise.all(
    ["families", "sensors", "sites", "regions", "cable", "terrain/terrain"].map(n => getJson(fetchImpl, `/atlas/${n}.json`)));
  return {
    manifest, families: fam.families, familyByKey: Object.fromEntries(fam.families.map(f => [f.key, f])),
    sensors: sen.sensors, sensorById: Object.fromEntries(sen.sensors.map(s => [s.id, s])), unplaced: sen.unplaced,
    sites: sit.sites, siteById: Object.fromEntries(sit.sites.map(s => [s.id, s])),
    regions: reg.regions, overview: reg.overview, cable, terrainMeta,
  };
}
