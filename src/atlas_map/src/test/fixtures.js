// A small bundle in the exact shape plan 1 writes.
export const FAMILIES = [
  { key: "seismic", label: "Seismic", color: "#d95926", glyph: "triangle" },
  { key: "chemistry", label: "Water properties", color: "#3987e5", glyph: "circle" },
];
const s = (id, extra) => ({
  id, instrumentId: `INSTRUMENT-${id}`, name: id, type: "ctd", family: "chemistry", lat: 45.8168, lon: -129.754,
  depth: 2607, depthRange: null, waterDepth: 2607, siteCode: "RS03AXBS", node: "MJ03A", refdes: null,
  location: "Axial Seamount Base", projects: ["Regional Cabled Array"], coszoRole: null, manufacturer: null, model: null,
  sources: [], arcadaId: null, corrections: [], status: "OPERATIONAL", statusGroup: "operating",
  statusSource: "Nereus snapshot", statusAsOf: "2026-09-19T07:41:44+00:00", access: [], site: "axial-seamount-base", region: "axial",
  ...extra,
});
export const SENSORS = [
  s("base-ctd", { refdes: "RS03AXBS-LJ03A-12-CTDPFB301",
    access: [{ kind: "erddap", label: "OOI ERDDAP (public, no login)", datasetId: "ooi-rs03axbs-lj03a-12-ctdpfb301",
               url: "https://erddap.dataexplorer.oceanobservatories.org/erddap/tabledap/ooi-rs03axbs-lj03a-12-ctdpfb301.html", how: "Download CSV." }] }),
  s("sp-ctd", { node: "SF03A", depth: 5, depthRange: [5, 200], location: "Axial Seamount Profiler", siteCode: "RS03AXPS" }),
  s("dp-ctd", { node: "DP03A", depth: 250, depthRange: [250, 2457], location: "Axial Seamount Deep Profiler", siteCode: "RS03AXPD",
    status: "NOT_DEPLOYED", statusGroup: "offline" }),
  s("axcc1", { family: "seismic", type: "seismometer", lat: 45.95468, lon: -130.0089, depth: 1527, waterDepth: 1527,
    site: "axial-seamount-central-caldera", location: "Axial Seamount Central Caldera", siteCode: null, node: null, status: "UNKNOWN", statusGroup: "unknown",
    statusSource: null, statusAsOf: null,
    access: [{ kind: "earthscope", label: "EarthScope FDSN", network: "OO", station: "AXCC1", channel: "HHZ", url: "https://service.earthscope.org/x", how: "Public." }] }),
  s("shelf-bpr", { family: "seismic", type: "seismometer", lat: 44.63731, lon: -124.30576, depth: null, waterDepth: null,
    site: "oregon-shelf", region: "shelf", location: "Oregon Shelf", siteCode: null, node: null, status: "PLANNED", statusGroup: "planned",
    statusSource: "Inventory: new COSZO sensor", statusAsOf: null, sources: ["https://coszo.org/x"],
    access: [{ kind: "documentation", label: "Documentation", url: "https://coszo.org/x", how: "No public data feed is known yet." }] }),
  s("unlocated-bpt", { lat: null, lon: null, name: "Axial Base bottom pressure and tilt", family: "seismic" }),
  // Unplaced: no position and no catalogued site (the real bundle has five, e.g. PI-MASSP-ASHES and the DAS experiments).
  s("pi-massp", { lat: null, lon: null, name: "ASHES PI mass spectrometer", type: "mass_spectrometer", site: null, region: null,
    location: null, siteCode: null, node: null, depth: null, waterDepth: null, status: "UNKNOWN", statusGroup: "unknown", statusSource: null, statusAsOf: null }),
];
export const SITES = [
  { id: "axial-seamount-base", name: "Axial Seamount Base", label: "Axial Base", region: "axial", lat: 45.8168, lon: -129.754,
    seafloor: 2614, sensorIds: ["base-ctd", "sp-ctd", "dp-ctd"], parts: ["Axial Seamount Base", "Axial Seamount Profiler", "Axial Seamount Deep Profiler"],
    column: [{ kind: "Shallow profiler", a: 5, b: 200 }, { kind: "Deep profiler", a: 250, b: 2457 }], unlocatedIds: ["unlocated-bpt"] },
  { id: "axial-seamount-central-caldera", name: "Axial Seamount Central Caldera", label: "Axial Central Caldera", region: "axial",
    lat: 45.95468, lon: -130.0089, seafloor: 1527, sensorIds: ["axcc1"], parts: ["Axial Seamount Central Caldera"], column: [], unlocatedIds: [] },
  { id: "oregon-shelf", name: "Oregon Shelf", label: "Oregon Shelf", region: "shelf", lat: 44.63731, lon: -124.30576,
    seafloor: 80, sensorIds: ["shelf-bpr"], parts: ["Oregon Shelf"], column: [], unlocatedIds: [] },
];
export const REGIONS = {
  overview: { ll: [-126.75, 45.02], dist: 650, polar: 0.84, az: 0, exag: 6 },
  regions: [
    { key: "axial", label: "Axial Seamount", lonMin: -180, lonMax: -129, view: { ll: [-129.885, 45.885], dist: 62, polar: 0.72, az: -0.3, exag: 3 } },
    { key: "shelf", label: "Oregon Shelf", lonMin: -124.9, lonMax: 0, view: { ll: [-124.62, 44.56], dist: 95, polar: 0.86, az: -0.25, exag: 4 } },
  ],
};
export const CABLE = {
  lines: [{ name: "North backbone: Pacific City landfall -> PN5A area", kind: "North backbone", route: "Pacific City landfall → PN5A area",
            accuracy: "charted", lengthKm: 267.5, source: "NOAA/BOEM", coords: [[-123.97, 45.2], [-127.28, 45.75]] }],
  nodes: [{ code: "PN5A", name: "PN5A (Mid-Plate)", accuracy: "charted", note: "", lon: -127.278, lat: 45.7556,
            description: "Placeholder node with minimal internal electronics, available for future network expansion. No sensors connect here." }],
  hidden: 5,
};
export const MANIFEST = { builtAt: "2026-09-23T18:00:00Z", total: 7, located: 5, sites: 3, corpusSnapshot: "2026-09-19", warnings: [], errors: [] };

export function bundleFixture() {
  const familyByKey = Object.fromEntries(FAMILIES.map(f => [f.key, f]));
  return {
    families: FAMILIES, familyByKey, sensors: SENSORS, sensorById: Object.fromEntries(SENSORS.map(x => [x.id, x])),
    sites: SITES, siteById: Object.fromEntries(SITES.map(x => [x.id, x])), unplaced: ["pi-massp"],
    regions: REGIONS.regions, overview: REGIONS.overview, cable: CABLE, terrainMeta: null, manifest: MANIFEST,
  };
}
