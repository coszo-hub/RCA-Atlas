// Pure helpers for the answer route, kept apart from the Worker entry so node --test can import them.

const EXCERPT_CHARS = 280;
const MAX_EVENTS = 5_000;
const MAX_EVIDENCE_CHARS = 18_000;

// The first ~280 characters of a chunk, whitespace-normalized, cut at a word with an ellipsis when longer.
export function excerpt(text) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= EXCERPT_CHARS) return normalized;
  const cut = normalized.slice(0, EXCERPT_CHARS), space = cut.lastIndexOf(" ");
  return `${(space > EXCERPT_CHARS * 0.6 ? cut.slice(0, space) : cut).replace(/[\s,;:.]+$/, "")}…`;
}

export function publicHit(hit) {
  return {
    chunk_id: hit.chunk_id,
    collection_id: hit.collection_id,
    collection_label: hit.collection_label,
    title: hit.title,
    score: hit.score,
    citations: hit.citations || [],
    metadata: hit.metadata || {},
    excerpt: excerpt(hit.text),
  };
}

// One key per cited source: the id plus its URL (a PI portal record lists several routes under one id).
export const sourceKey = (id, url) => `${id}|${url || ""}`;

// The DAS experiments by the names people type, the map's own labels included (DAS21, DAS24, DAS25). The corpus
// names them by year ("2021 RCA Distributed Acoustic and Temperature Sensing experiment"), so each carries the
// words that retrieve its records (search), the text that identifies them (record), and how to name it to the
// model (about). Specific routes come before their experiment, so "MultiDAS 2025" is MultiDAS.
export const DAS_PRODUCTS = [
  { key: "multidas", asked: /\bmulti[\s-]?das\b/, record: /multidas/i,
    about: "the 2025–26 multi-span DAS dataset (MultiDAS, Nokia), part of the 2025–2026 RCA Distributed Acoustic Sensing experiment",
    search: "2025–2026 RCA Distributed Acoustic Sensing experiment DAS25 MultiDAS" },
  { key: "optodas", asked: /\bopto[\s-]?das\b/, record: /optodas/i,
    about: "the 2025–26 OptoDAS dataset, part of the 2025–2026 RCA Distributed Acoustic Sensing experiment",
    search: "2025–2026 RCA Distributed Acoustic Sensing experiment DAS25 OptoDAS" },
  { key: "das21", asked: /\bdas[\s-]?21\b|\b2021\b[^?]*\b(?:das|dts)\b|\b(?:das|dts)\b[^?]*\b2021\b|\boptasense\b|\bsilixa\b/, record: /2021 RCA Distributed Acoustic/i,
    about: "DAS21, the 2021 conventional DAS experiment (the 2021 RCA Distributed Acoustic and Temperature Sensing experiment, with OptaSense and Silixa interrogators)",
    search: "2021 RCA Distributed Acoustic and Temperature Sensing experiment OptaSense Silixa DTS" },
  { key: "das24", asked: /\bdas[\s-]?24\b|\b2024\b[^?]*\bdas\b|\bdas\b[^?]*\b2024\b|\brapid\b/, record: /2024 RCA Distributed Acoustic|\bdas24\b/i,
    about: "DAS24, the 2024 multiplexed DAS experiment (the 2024 RCA Distributed Acoustic Sensing experiment, RAPID)",
    search: "2024 RCA Distributed Acoustic Sensing experiment DAS24 dphi RAPID" },
  { key: "das25", asked: /\bdas[\s-]?25\b|\b202[56]\b[^?]*\bdas\b|\bdas\b[^?]*\b202[56]\b/, record: /2025–2026 RCA Distributed Acoustic|\bdas25\b/i,
    about: "DAS25, the 2025–2026 RCA Distributed Acoustic Sensing experiment: the 2025–26 OptoDAS and 2025–26 multi-span DAS (MultiDAS) datasets",
    search: "2025–2026 RCA Distributed Acoustic Sensing experiment DAS25 MultiDAS OptoDAS" },
];
// Field shorthand the corpus spells out. "dv/v" appears once in the OOI article on Kidiwela et al. (2026), whose
// text says "seismic velocity" and "ambient seismic noise interferometry"; in a long question the shorthand lost
// to every paper matching "Cascadia subduction zone".
const SHORTHAND = [
  { asked: /(?:\bd|δ)v\s*\/\s*v\b/i, search: "relative seismic velocity change dv/v ambient seismic noise interferometry temporal velocity variations" },
];

// The words the corpus search and the evidence ranking use for a question: the question, the corpus name of a
// named DAS experiment, and spelled-out shorthand.
export function searchText(question) {
  const q = String(question || "");
  const extra = [namedDas(q)?.search, ...SHORTHAND.filter((x) => x.asked.test(q)).map((x) => x.search)].filter(Boolean);
  return extra.length ? `${q} ${extra.join(" ")}` : q;
}

export const namedDas = (question) => DAS_PRODUCTS.find((p) => p.asked.test(String(question || "").toLowerCase())) ?? null;

// The four DAS datasets as the RCA team names them, one download link each. The corpus lists the 2021
// experiment's six sub-folders as routes of their own (OptaSense north and south cable receive and transmit
// fibers, Silixa DAS and DTS); they share one parent folder, which is that dataset's link.
export const DAS_DATASETS = [
  { route: /piweb\.ooirsn\.uw\.edu\/das\/data\//i, title: "2021 conventional DAS (OptaSense and Silixa)", url: "http://piweb.ooirsn.uw.edu/das/data/" },
  { route: /\/das24\/data\//i, title: "2024 multiplexed DAS", url: "http://piweb.ooirsn.uw.edu/das24/data/" },
  { route: /\/das25\/data\/optodas\//i, title: "2025–26 OptoDAS", url: "http://piweb.ooirsn.uw.edu/das25/data/OptoDAS/" },
  { route: /\/das25\/data\/multidas\//i, title: "2025–26 multi-span DAS (MultiDAS)", url: "http://piweb.ooirsn.uw.edu/das25/data/MultiDAS/" },
];
export const dasDataset = (url) => DAS_DATASETS.find((d) => d.route.test(url || "")) ?? null;

// A PI portal availability record names every download route in its text ("are available to download from
// DAS25 MultiDAS (http://…); DAS25 OptoDAS (http://…)."), but carries only the first as its citation, so the
// other routes never reached the answer's sources. Each named route becomes a citation of its own.
const ROUTE_LIST = /available to download from (.+?\))\.(?:\s|$)/;
const ROUTE = /([^;()]+?)\s*\((https?:\/\/[^\s)]+)\)/g;
export function withRouteCitations(hit) {
  const list = ROUTE_LIST.exec(String(hit.text || ""));
  if (!list) return hit;
  const labels = new Map([...list[1].matchAll(ROUTE)].map(([, label, url]) => [url, label.trim()]));
  const cited = hit.citations || [], base = cited[0] || { source_id: hit.chunk_id };
  // The record's own citation carries the corpus name ("Shared RCA and COSZO Instruments corpus"); name its route.
  const own = cited.map((c) => (labels.has(c.url) && /shared rca and coszo instruments corpus/i.test(c.title || "") ? { ...c, title: labels.get(c.url) } : c));
  const added = [...labels].filter(([url]) => !cited.some((c) => c.url === url))
    .map(([url, title]) => ({ ...base, source_id: base.source_id || hit.chunk_id, title, url }));
  // A DAS route is cited as its dataset: the 2021 record's six sub-folders become its one link.
  const seen = new Set();
  const routes = [...own, ...added].map((c) => { const d = dasDataset(c.url); return d ? { ...c, title: d.title, url: d.url } : c; })
    .filter((c) => !c.url || (!seen.has(c.url) && seen.add(c.url)));
  return { ...hit, citations: routes };
}

// The evidence text for the prompt: each hit under a header with its source numbers.
export function evidencePackage(hits, sourceNumbers) {
  const sections = [];
  let remaining = MAX_EVIDENCE_CHARS;
  for (const hit of hits) {
    if (remaining <= 0) break;
    const refs = [...new Set((hit.citations || []).map((c) => sourceNumbers.get(sourceKey(c.source_id || hit.chunk_id, c.url))).filter(Boolean))];
    const header = `${hit.title}${refs.length ? ` | sources: ${refs.map((n) => `[${n}]`).join(" ")}` : ""}\n`;
    const text = String(hit.text || "").slice(0, Math.max(0, remaining - header.length));
    sections.push(`${header}${text}`);
    remaining -= header.length + text.length + 2;
  }
  return sections.join("\n\n");
}

// Rows of a daily UW hypo71 file (yyyymmdd HHMM SS.SS latD latM lonD lonM depth MW NWR GAP DMIN RMS ERH ERZ ID PMom SMom),
// longitude degrees west. Only rows for `stamp` (yyyymmdd) with all 18 columns count, as the live count always has.
export function hypo71Rows(text, stamp) {
  return String(text || "").split(/\r?\n/).map((line) => line.trim().split(/\s+/))
    .filter((parts) => parts.length >= 18 && parts[0] === stamp);
}

export function parseHypo71Events(text, stamp) {
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };
  const round = (v, d) => (v == null ? null : Math.round(v * 10 ** d) / 10 ** d);
  return hypo71Rows(text, stamp).slice(0, MAX_EVENTS).map((p) => {
    const hhmm = p[1].padStart(4, "0");
    const ms = Date.UTC(+p[0].slice(0, 4), +p[0].slice(4, 6) - 1, +p[0].slice(6, 8), +hhmm.slice(0, 2), +hhmm.slice(2, 4))
      + Math.round((num(p[2]) ?? 0) * 1000);   // 60.00 s rolls into the next minute
    const lat = num(p[3]) != null && num(p[4]) != null ? num(p[3]) + num(p[4]) / 60 : null;
    const lon = num(p[5]) != null && num(p[6]) != null ? -(num(p[5]) + num(p[6]) / 60) : null;
    return { time: new Date(ms).toISOString(), lat: round(lat, 6), lon: round(lon, 6), depth_km: num(p[7]), mag: num(p[8]) };
  });
}

// The catalog is one file per UTC day, but "today" means the asker's day: in Seattle at 7 pm that is already
// tomorrow in UTC. With the asker's IANA time zone the window is their calendar day (today, yesterday, or an explicit
// YYYY-MM-DD), which spans one or two UTC files; without one (the published RCA Atlas page) it stays the UTC day.
const DAY_MS = 86_400_000;
function validZone(tz) {
  try { new Intl.DateTimeFormat("en-US", { timeZone: tz }); return tz; } catch { return "UTC"; }
}
const ymd = (date, tz) => new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
function zoneOffset(tz, ms) {   // local wall time minus UTC, in ms, at the instant ms
  const f = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }).formatToParts(new Date(ms)).map((p) => [p.type, p.value]));
  return Date.UTC(+f.year, +f.month - 1, +f.day, +f.hour, +f.minute, +f.second) - Math.floor(ms / 1000) * 1000;
}
function localMidnight(day, tz) {
  const wall = Date.UTC(+day.slice(0, 4), +day.slice(5, 7) - 1, +day.slice(8, 10));
  const guess = wall - zoneOffset(tz, wall);
  return wall - zoneOffset(tz, guess);   // again at the guess, in case a DST change falls between
}

export function axialDayWindow(question, { tz, now = new Date() } = {}) {
  const q = String(question || "").toLowerCase();
  if (!/axial/.test(q) || !/(how many|count|number of)/.test(q) || !/earthquake/.test(q)) return null;
  const zone = tz ? validZone(tz) : "UTC", today = ymd(now, zone);
  const explicit = q.match(/\b(20\d{2}-\d{2}-\d{2})\b/);
  let day;
  if (explicit) day = explicit[1];
  else if (q.includes("yesterday")) day = ymd(new Date(localMidnight(today, zone) - DAY_MS / 2), zone);
  else if (q.includes("today")) day = today;
  else return null;
  const start = localMidnight(day, zone), next = new Date(start + DAY_MS * 1.5);
  const end = localMidnight(ymd(next, zone), zone);
  const stamps = [];
  for (let t = Date.UTC(new Date(start).getUTCFullYear(), new Date(start).getUTCMonth(), new Date(start).getUTCDate()); t < end; t += DAY_MS) {
    stamps.push(new Date(t).toISOString().slice(0, 10).replaceAll("-", ""));
  }
  const label = new Intl.DateTimeFormat("en-US", { timeZone: zone, weekday: "long", month: "long", day: "numeric" }).format(new Date(start));
  const zoneName = new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "long" }).formatToParts(new Date(start))
    .find((p) => p.type === "timeZoneName")?.value ?? zone;
  return { day, tz: zone, today: day === today, start: new Date(start), end: new Date(end), stamps, label, zoneName };
}

// Every event from the fetched files ([text, stamp] pairs) that falls inside the window, in time order.
export function eventsInWindow(files, window) {
  const from = window.start.toISOString(), to = window.end.toISOString();
  return files.flatMap(([text, stamp]) => parseHypo71Events(text, stamp))
    .filter((e) => e.time >= from && e.time < to)
    .sort((a, b) => (a.time < b.time ? -1 : 1));
}

// The synthesis prompt. Sources are numbered in answer_citations order; the evidence headers carry the same
// numbers, and the model cites them as [n] so the interface can link each claim to its source (and its place).
// Inventory questions ("which seismometers are at Axial?") must list every match, so they retrieve and keep more
// evidence than a narrative question: Axial alone has eight seismic stations, past the default six. Either a
// generic word or a named instrument type counts, alongside a place.
const INSTRUMENT_WORDS = /\b(sensors?|instruments?|equipment|seismometers?|seismic stations?|hydrophones?|tiltmeters?|accelerometers?|pressure sensors?|ctds?|adcps?|cameras?|thermistors?|fluorometers?)\b/;
const PLACE_WORDS = /\b(sites?|location|located|deployed|seafloor|southern hydrate ridge|hydrate ridge|axial|caldera|ashes|international district|oregon shelf|oregon offshore|slope base|summit)\b/;

export function isInstrumentInventoryQuestion(question) {
  const q = String(question || "").toLowerCase();
  return INSTRUMENT_WORDS.test(q) && PLACE_WORDS.test(q);
}

export function answerPrompt({ question, evidence, sources, mode, product = null }) {
  const sourceListText = sources.map((c, i) => `[${i + 1}] ${c.title}`).join("; ");
  const namedProductInstruction = product
    ? `The user specifically named ${product}; answer only about it. Do not include other experiments, routes, file formats, instruments, or data types unless the evidence assigns them to it.`
    : "";
  const compactInstruction = mode === "compact"
    ? `This is a data-availability, download, or list question. ${namedProductInstruction} Give a one-sentence direct answer. Then, for each dataset or experiment, one plain line naming it by its source's title, with its years, coverage and file formats, cited with its source number; when one dataset has several numbered sources (download routes), add one hyphen bullet per source, giving its name and only what the evidence ties to that source itself. Sub-folders that the evidence names inside one source (such as the 2021 dataset's OptaSense and Silixa folders) are described in one bullet of that dataset, not bullets of their own. Add one bullet for the folder layout or a caveat (such as very many files per day) when the evidence gives one. Include every numbered download source; never drop one. Leave out evidence that is not a downloadable dataset (papers, methods, policies) entirely, without remarking on it. Use no capability descriptions, deployment background, or calibration details. Keep the whole answer under 230 words. The interface links each cited source.`
    : "Write a complete, useful research answer from the evidence, but do not pad it with loosely related instruments, background, or speculation. For an instrument inventory question, identify every matching named instrument record you can support, then describe its identity, site or location, capabilities or measurements, and where its data are available when the evidence provides that. Never infer that a sensor type is absent merely because it is not in a partial evidence set; say that the retrieved evidence is incomplete instead.";
  const formatInstruction = mode === "compact"
    ? "Use plain text, with no Markdown hashes or asterisks, and no URLs. Obey the 230-word limit."
    : "Structure the response as plain text: a brief direct answer, then section labels on their own lines and hyphen bullets where there are multiple locations, instruments, or findings. Do not use Markdown hashes or asterisks.";
  const citationInstruction = "Cite the evidence with the bracketed source numbers [n] from the evidence headers (for example [2] or [1, 3]), placed directly after the claim they support. Use only those numbers. Do not include chunk IDs, source IDs, database identifiers, URLs, titles in brackets, or any other provenance notation in the answer text; the interface renders the numbered source list separately below the answer.";
  return `Retrieved RCA Atlas evidence:\n\n${evidence}\n\n---\nQuestion: ${question}\n\nRCA Atlas defaults to the OOI Regional Cabled Array and COSZO. Unless the user explicitly asks for a global comparison, answer in that scope and exclude tangential sites or literature outside it. First compare the individual named records in the evidence against the question. Then answer the user's exact question directly. Do not lead with a generic instrument definition when the user asks which instruments exist or where they are. ${compactInstruction} ${formatInstruction} ${mode === "compact" ? "If a requested dataset is missing from the evidence, say so in one sentence." : "State clearly what the evidence does not establish."} ${citationInstruction} Do not invent live values or tool results. Evidence sources available to you: ${sourceListText}`;
}
