// Where an Ask Atlas answer's evidence is on the map. Pure: the Worker response and the atlas bundle in,
// numbered evidence out. `n` is the 1-based index into answer_citations, the numbers the answer cites as [n].
//   located: sensors, sites, and DAS cables, each with a position (a cable's is a point on its route)
//   documents: everything else (papers, pages, guides), listed as further reading
//   events: the Axial quake-count route's hypocentres, when the Worker returns them
//   count: that route's day and count, even when it returns no events (the deployed Worker before `events`)

export const SITE_COLOR = "#ecebe6";

// DAS experiments by their PI-portal route (or name), and the DAS coverage layers (das.json) that draw them.
// DAS24 ran on the south cable's first span, which is the OptoDAS layer's extent.
const DAS_ROUTES = [
  { id: "das25-multidas", url: /\/das25\/data\/multidas/i, text: /\bmulti[\s-]?(?:das|span)\b/i, kinds: ["multidas"], code: "MultiDAS", where: "North + south cables", label: "DAS25 MultiDAS, 2025–26" },
  { id: "das25-optodas", url: /\/das25\/data\/optodas/i, text: /\boptodas\b/i, kinds: ["optodas"], code: "OptoDAS", where: "South cable, first span", label: "DAS25 OptoDAS, 2025–26" },
  { id: "das25", url: /\/das25\//i, kinds: ["multidas", "optodas"], code: "DAS25", where: "North + south cables", label: "DAS25 fibre sensing, 2025–26" },
  { id: "das24", url: /\/das24\//i, layers: ["optodas-south-first-span"], code: "DAS24", where: "South cable, first span", label: "DAS24 RAPID, 2024" },
  { id: "das21-north", url: /\/das\/.*north ?cable/i, layers: ["conventional-north"], code: "DAS21", where: "North cable", label: "2021 DAS community test, north cable" },
  { id: "das21-south", url: /\/das\/.*south ?cable/i, layers: ["conventional-south"], code: "DAS21", where: "South cable", label: "2021 DAS community test, south cable" },
  { id: "das21", url: /piweb\.ooirsn\.uw\.edu\/das\//i, kinds: ["conventional"], code: "DAS21", where: "North + south cables", label: "2021 DAS community test" },
];

const RECORD_KEYS = ["Instrument", "Canonical identifier", "Type", "Projects", "Location", "Status", "Deployment state", "Aliases",
  "Sensor components", "Manufacturer", "Model", "Notes", "Measurement roles"];

const cache = new WeakMap();
function indexOf(bundle) {
  if (cache.has(bundle)) return cache.get(bundle);
  const byInstrument = new Map(), byArcada = new Map(), byCode = new Map(), byUrl = new Map();
  for (const s of bundle.sensors ?? []) {
    byInstrument.set(s.instrumentId, s);
    if (s.arcadaId) byArcada.set(s.arcadaId, s);
    for (const code of [s.id, s.refdes]) if (code) byCode.set(code.toUpperCase(), s);
    for (const u of new Set([...(s.sources ?? []), ...(s.access ?? []).map(a => a.url)])) {
      if (!u) continue;
      const k = normUrl(u); byUrl.set(k, [...(byUrl.get(k) ?? []), s]);
    }
  }
  // Site names and their short labels ("Axial Central Caldera"), longest first. Several sites share a name
  // (four "Southern Hydrate Ridge Summit" stations); the one with the most sensors stands for the name.
  const names = new Map();
  for (const site of bundle.sites ?? []) {
    for (const name of [site.name, site.label?.split(" · ")[0]]) {
      if (!name || name.length < 8) continue;
      const k = name.toLowerCase(), prev = names.get(k);
      if (!prev || site.sensorIds.length > prev.sensorIds.length) names.set(k, site);
    }
  }
  const siteNames = [...names].sort((a, b) => b[0].length - a[0].length);
  const idx = { byInstrument, byArcada, byCode, byUrl, siteNames };
  cache.set(bundle, idx);
  return idx;
}

const normUrl = u => String(u).trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/+$/, "");
const escape = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// The hits behind a citation: those citing the same source id and URL (the Worker's own dedupe key), else the same id.
function hitsFor(cite, hits) {
  const key = h => (h.citations ?? []).map(c => `${c.source_id || h.chunk_id}|${c.url || ""}`);
  const exact = hits.filter(h => key(h).includes(`${cite.id}|${cite.url || ""}`));
  return exact.length ? exact : hits.filter(h => (h.citations ?? []).some(c => (c.source_id || h.chunk_id) === cite.id));
}

// Sensors named in text by id or refdes, EarthScope station (station_OO_AXCC1, ds.iris.edu/mda/OO/AXCC1), in order.
function sensorsIn(text, idx) {
  const found = [];
  const add = s => { if (s && !found.includes(s)) found.push(s); };
  for (const m of text.matchAll(/station_([A-Z0-9]{2})_([A-Z0-9]{3,6})\b|\/mda\/([A-Z0-9]{2})\/([A-Z0-9]{3,6})\b|[A-Z0-9]+(?:-[A-Z0-9]+){1,4}/gi)) {
    if (m[1] || m[3]) add(idx.byCode.get(`EARTHSCOPE-${m[1] ?? m[3]}-${m[2] ?? m[4]}`.toUpperCase()));
    else add(idx.byCode.get(m[0].toUpperCase()));
  }
  return found;
}

// One sensor is that sensor; several at one site are the site; spread over sites, the first named.
function oneOf(sensors, bundle) {
  if (!sensors.length) return null;
  const sites = new Set(sensors.map(s => s.site));
  if (sensors.length > 1 && sites.size === 1 && sensors[0].site) return siteItem(bundle.siteById[sensors[0].site]);
  return sensorItem(sensors[0], bundle);
}

function dasRoute(urls, texts) {
  return DAS_ROUTES.find(r => urls.some(u => r.url.test(u))) ?? DAS_ROUTES.find(r => r.text && texts.some(t => r.text.test(t))) ?? null;
}

function cableItem(route, bundle) {
  const layers = (bundle.das?.layers ?? []).filter(l => route.layers?.includes(l.id) || route.kinds?.includes(l.kind));
  if (!layers.length) return null;
  // Its anchor (tag, card, flights) is the middle of the longest layer.
  const len = l => l.coords.slice(1).reduce((a, c, i) => a + Math.hypot(c[0] - l.coords[i][0], c[1] - l.coords[i][1]), 0);
  const longest = layers.reduce((a, b) => (len(b) > len(a) ? b : a));
  const [lon, lat] = longest.coords[Math.floor(longest.coords.length / 2)];
  return { kind: "cable", id: route.id, layers: layers.map(l => l.id), lon, lat, depth: null, family: "fiber", color: layers[0].color,
    code: route.code, label: route.label, site: route.where, siteId: null, refdes: null };
}

function sensorItem(s, bundle) {
  const site = s.site ? bundle.siteById[s.site] : null;
  if (s.lat == null && !site) {
    // No position and no site: a DAS experiment draws as its cable; anything else is not on the map.
    const route = s.family === "fiber" && dasRoute([...(s.sources ?? []), ...(s.access ?? []).map(a => a.url).filter(Boolean)], [s.name]);
    return route ? cableItem(route, bundle) : null;
  }
  return { kind: "sensor", id: s.id, lon: s.lon ?? site.lon, lat: s.lat ?? site.lat, depth: s.depth ?? s.waterDepth ?? site?.seafloor ?? null,
    family: s.family, color: bundle.familyByKey?.[s.family]?.color ?? SITE_COLOR, code: codeOf(s), label: s.name,
    site: site ? shortSite(site.label) : "", siteId: site?.id ?? null, refdes: s.refdes ?? s.id };
}

function siteItem(site) {
  if (!site) return null;
  return { kind: "site", id: site.id, lon: site.lon, lat: site.lat, depth: site.seafloor ?? null, family: null, color: SITE_COLOR,
    code: "Site", label: site.name, site: shortSite(site.label), siteId: site.id, refdes: null };
}

const describe = s => [[s.manufacturer, s.model].filter(Boolean).join(" "), s.type?.replaceAll("_", " ")].filter(Boolean).join(" · ");

// The instrument's own code: the last part of its refdes (BOTPTA303) or EarthScope station (HYS12).
const codeOf = s => (s.refdes ?? s.id).split("-").pop();

export function shortSite(label = "") {
  let s = label.split(" · ")[0].replace(/^Axial Seamount /, "Axial ").replace(/^Southern Hydrate Ridge/, "Hydrate Ridge")
    .replace("International", "Intl").replace("Hydrothermal Field", "Vent Field");
  if (/^Axial /.test(s) && s !== "Axial Base") s = s.replace(/^Axial /, "");
  return s;
}

// Prose is quoted; an instrument record ("Instrument: … Type: … Manufacturer: …") reads as a short description.
export function readableExcerpt(text) {
  const t = String(text ?? "").trim();
  if (!t) return { excerpt: "", quote: false };
  if (!/^Instrument: /.test(t)) return { excerpt: t, quote: true };
  const re = new RegExp(`(${RECORD_KEYS.map(escape).join("|")}): `, "g"), f = {};
  const marks = [...t.matchAll(re)];
  marks.forEach((m, i) => { f[m[1]] = t.slice(m.index + m[0].length, marks[i + 1]?.index ?? t.length).replace(/[…\s]+$/, "").trim(); });
  const useful = v => v && !/^(none|not separately enumerated)$/i.test(v);
  const parts = [[f.Manufacturer, f.Model].filter(useful).join(" "), f.Type?.replaceAll("_", " "), f["Measurement roles"], f["Sensor components"]];
  return { excerpt: parts.filter(useful).join(" · "), quote: false };
}

function locate(cite, hits, idx, bundle) {
  // 1. Instrument ids: the source itself, or the instrument chunk behind it.
  for (const id of [cite.id, ...hits.flatMap(h => [h.chunk_id, ...(h.citations ?? []).map(c => c.source_id)])]) {
    const m = /^(ARCADA-)?INSTRUMENT-(?:CHUNK-)?([0-9a-f]+)$/i.exec(id ?? "");
    const s = m && (m[1] ? idx.byArcada.get(`ARCADA-INSTRUMENT-${m[2]}`) : idx.byInstrument.get(`INSTRUMENT-${m[2].slice(0, 18)}`));
    if (s) return sensorItem(s, bundle);
  }
  const urls = [cite.url, ...hits.flatMap(h => (h.citations ?? []).map(c => c.url))].filter(Boolean);
  const titles = [cite.title, ...hits.map(h => h.title)].filter(Boolean);
  const texts = [...titles, ...hits.flatMap(h => [JSON.stringify(h.metadata ?? {}), h.excerpt])].filter(Boolean);
  // 2. A refdes, canonical id, or EarthScope station in the titles, metadata, excerpts or URL.
  const named = oneOf(sensorsIn([...texts, ...urls].join("\n"), idx), bundle);
  if (named) return named;
  // 3. A DAS experiment's portal route.
  const route = dasRoute(urls, titles);
  if (route) return cableItem(route, bundle);
  // 4. A URL that is a sensor's own data or documentation page.
  for (const u of urls) {
    const owners = idx.byUrl.get(normUrl(u)) ?? [], hit = oneOf(owners, bundle);
    if (hit && (owners.length === 1 || hit.kind === "site")) return hit;
  }
  // 5. A site named in a title or excerpt (the earliest mention wins).
  for (const t of texts) {
    let best = null;
    for (const [name, site] of idx.siteNames) {
      const at = t.search(new RegExp(`\\b${escape(name)}\\b`, "i"));
      if (at >= 0 && (!best || at < best.at)) best = { at, site };
    }
    if (best) return siteItem(best.site);
  }
  return null;
}

function events(list) {
  if (!Array.isArray(list)) return null;
  return list.filter(e => Number.isFinite(e?.lat) && Number.isFinite(e?.lon) && e.time)
    .sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0))
    .map((e, i) => ({ n: i + 1, time: e.time, lat: e.lat, lon: e.lon, depth_km: Number.isFinite(e.depth_km) ? e.depth_km : null,
      mag: Number.isFinite(e.mag) ? e.mag : null }));
}

function countOf(response, ev) {
  const hint = (response.tool_hints ?? []).find(t => t.name === "axial_count_events");
  if (!hint) return null;
  const m = /There were ([\d,]+) /.exec(response.answer ?? "");
  return { day: hint.input_schema?.day ?? null, n: ev ? ev.length : m ? +m[1].replaceAll(",", "") : null };
}

export function resolveEvidence(response, bundle) {
  if (!response || typeof response !== "object") return { located: [], documents: [], events: null, count: null };
  const idx = indexOf(bundle), hits = Array.isArray(response.hits) ? response.hits : [];
  const located = [], documents = [];
  (response.answer_citations ?? []).forEach((cite, i) => {
    const n = i + 1, behind = hitsFor(cite, hits);
    const title = cite.title || behind[0]?.title || cite.id;
    let { excerpt, quote } = readableExcerpt(behind.map(h => h.excerpt).find(Boolean));
    const item = locate(cite, behind, idx, bundle);
    // A sensor without a prose excerpt (the deployed Worker sends none) is described from the bundle.
    if (item?.kind === "sensor" && !quote) ({ excerpt, quote } = { excerpt: describe(bundle.sensorById[item.id]) || excerpt, quote: false });
    if (item) located.push({ n, ...item, title, excerpt, quote, sourceUrl: cite.url || null });
    else documents.push({ n, title, url: cite.url || null, excerpt, quote });
  });
  const ev = events(response.events);
  return { located, documents, events: ev?.length ? ev : null, count: countOf(response, ev) };
}
