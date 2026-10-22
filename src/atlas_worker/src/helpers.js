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

// Papers are never excerpted to readers: their citation links to the paper, where it can be read in full.
export function publicHit(hit) {
  return {
    chunk_id: hit.chunk_id,
    collection_id: hit.collection_id,
    collection_label: hit.collection_label,
    title: hit.title,
    score: hit.score,
    citations: hit.citations || [],
    metadata: hit.metadata || {},
    excerpt: sourceKind(hit) === "scientific literature" ? "" : excerpt(hit.text),
  };
}

const DOI_URL = /^https?:\/\/(?:dx\.)?doi\.org\//i;

// One key per cited source: the id plus its URL (a PI portal record lists several routes under one id). A paper is
// keyed by its DOI link, so its abstract, its full text and another collection's copy are one numbered source.
export const sourceKey = (id, url) => (DOI_URL.test(url || "") ? `doi|${String(url).toLowerCase().replace(/^http:/, "https:")}` : `${id}|${url || ""}`);

// The paper a hit belongs to, or null: the key the full-text layer is matched on.
export function paperKey(hit) {
  if (sourceKind(hit) !== "scientific literature") return null;
  const c = (hit.citations || [])[0] || {};
  return sourceKey(c.source_id || hit.chunk_id, c.url);
}

export const FULLTEXT_COLLECTION = "literature_fulltext";
// Four passages a paper and eight in all (a paper alone may take all eight), skipping passages that mostly repeat
// the evidence (a paper's first page restates its abstract): with the question searched part by part, that brings
// every asked fact of the full-text eval questions to the model (five passages missed two of them).
const FULLTEXT_PER_PAPER = 4;
const FULLTEXT_MAX = 8;
const PASSAGE_CHARS = 1_800;
// With passages the whole prompt stays near 26,000 characters (~5,800 tokens at Groq's ~4.5 characters a token):
// Groq's free tier refuses a request over 8,000 tokens a minute, and the 34,000-character prompts were refused.
const FULLTEXT_CHARS = 11_000;
const MAIN_WITH_FULLTEXT_CHARS = 12_000;
const REPEAT_RUN = 8;
const REPEAT_SHARE = 0.2;
const isLayer = (hit) => hit.layer === true || hit.collection_id === FULLTEXT_COLLECTION;

// The keys the passage search knows a paper by: its DOI (no resolver prefix) and its catalog or document ID. A
// paper the evidence only names by DOI (an OOI page "adapted from Philip et al., 2023, doi: 10.1126/...") counts
// too: its full text answers what the summary leaves out.
const DOI_IN_TEXT = /\b10\.\d{4,9}\/[^\s"<>,;)\]]+/gi;
const mentionedDois = (hits) => hits.flatMap((hit) => (String(hit.text || "").match(DOI_IN_TEXT) || [])
  .map((doi) => doi.toLowerCase().replace(/[.]+$/, "")));

export function paperKeys(hits) {
  const keys = [];
  for (const hit of hits) {
    if (!paperKey(hit)) continue;
    for (const c of hit.citations || []) {
      if (DOI_URL.test(c.url || "")) keys.push(String(c.url).toLowerCase().replace(DOI_URL, ""));
      if (c.source_id) keys.push(String(c.source_id));
    }
  }
  return [...new Set([...keys, ...mentionedDois(hits)])].slice(0, 12);
}

// A question asking two things ("how fast ..., and how many ...") is searched part by part: ranked for the whole
// question, the passage answering its second part fell behind those answering its first.
const PART_BREAK = /,?\s+and\s+(?=(?:how|what|which|when|where|who|why)\b)|[;?]\s*/i;
export function questionParts(question) {
  const parts = String(question || "").split(PART_BREAK).map((p) => p.trim()).filter((p) => p.length > 12);
  return parts.length > 1 ? parts.slice(0, 3) : [String(question || "")];
}

// Several ranked lists, alternated: each part's best passage, then each part's next, without repeats.
export function interleave(lists) {
  const out = [], seen = new Set();
  for (let i = 0; lists.some((l) => i < l.length); i += 1) {
    for (const list of lists) {
      const hit = list[i];
      if (hit && !seen.has(hit.chunk_id)) { seen.add(hit.chunk_id); out.push(hit); }
    }
  }
  return out;
}

// Full-text passages for the papers already in the evidence, best first: at most four per paper and eight in all,
// so the layer adds to a paper's evidence and never displaces another source.
export function fullTextFor(hits, passages) {
  const papers = new Set([...hits.map(paperKey).filter(Boolean),
    ...mentionedDois(hits).map((doi) => sourceKey("", `https://doi.org/${doi}`))]);
  const seen = runsOf(hits.map((hit) => hit.text), REPEAT_RUN);
  const candidates = (passages || []).filter((p) => isLayer(p) && papers.has(paperKey(p)));
  // One paper alone may fill every slot; several share them.
  const cap = new Set(candidates.map(paperKey)).size > 1 ? FULLTEXT_PER_PAPER : FULLTEXT_MAX;
  const perPaper = new Map();
  const chosen = [];
  for (const passage of candidates) {
    const key = paperKey(passage);
    if ((perPaper.get(key) || 0) >= cap) continue;
    const own = [...runsOf([passage.text], REPEAT_RUN)];
    if (own.length && own.filter((run) => seen.has(run)).length / own.length > REPEAT_SHARE) continue;
    perPaper.set(key, (perPaper.get(key) || 0) + 1);
    chosen.push(passage);
    if (chosen.length >= FULLTEXT_MAX) break;
  }
  return chosen;
}

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
// Each was checked against the corpus, where the spelled-out form is the common one (OSB 1 vs "Slope Base" 1,399;
// IDF 0 vs "International District" 604). CI and ETS match only in capitals; as words they mean other things.
const SHORTHAND = [
  { asked: /(?:\bd|δ)v\s*\/\s*v\b/i, search: "relative seismic velocity change dv/v ambient seismic noise interferometry temporal velocity variations" },
  { asked: /\bamc\b/i, search: "axial magma chamber" },
  { asked: /\bcsz\b/i, search: "Cascadia subduction zone" },
  { asked: /\bjdf\b/i, search: "Juan de Fuca" },
  { asked: /\bv?lfes?\b/i, search: "low-frequency earthquakes" },
  { asked: /\bvlfes?\b/i, search: "very low frequency earthquakes" },
  { asked: /\bsses?\b/i, search: "slow slip events" },
  { asked: /\bETS\b/, search: "episodic tremor and slip" },
  { asked: /\bnvt\b/i, search: "non-volcanic tremor" },
  { asked: /\bobss?\b/i, search: "ocean bottom seismometer" },
  { asked: /\bonc\b/i, search: "Ocean Networks Canada" },
  { asked: /\bCI\b/, search: "Cascadia Initiative" },
  { asked: /\bidf\b/i, search: "International District hydrothermal field" },
  { asked: /\bosb\b/i, search: "Oregon Slope Base" },
  { asked: /\bshr\b/i, search: "Southern Hydrate Ridge" },
  { asked: /\bzplsc?\b/i, search: "bio-acoustic sonar zooplankton" },
  { asked: /\bvp\s*\/\s*vs\b/i, search: "P-wave to S-wave velocity ratio" },
  { asked: /\bt[- ]phases?\b/i, search: "T-phase hydroacoustic" },
  { asked: /\bmorb\b/i, search: "mid-ocean ridge basalt" },
  { asked: /\brtdd\b/i, search: "real-time double-difference earthquake location" },
  { asked: /\bbprs?\b/i, search: "bottom pressure recorder" },
  { asked: /\bapgs?\b/i, search: "absolute pressure gauge" },
  { asked: /\beew\b/i, search: "earthquake early warning" },
  { asked: /\bmef\b/i, search: "Main Endeavour Field" },
  { asked: /\bgnss[- ]a\b/i, search: "GNSS-Acoustic seafloor geodesy" },
  { asked: /\bbotpt\b/i, search: "bottom pressure and tilt" },
  // Replaced, not added: the token "DAS" itself pulls in every DAS-titled paper, which buried "seismic ocean
  // thermometry" behind them even with the phrase added.
  // Kept in data questions ("How do I get the DAS data?"), whose download records the token itself finds.
  { asked: /\bdas\b/gi, search: "distributed acoustic sensing", replace: true,
    unless: /\b(?:download|get|access|available|availability|files?|data|dataset)\b/i },
];

// The words the corpus search and the evidence ranking use for a question: the question, the corpus name of a
// named DAS experiment, and spelled-out shorthand.
export function searchText(question) {
  // An acronym's plural ("CTDs", "ADCPs") is not the word the records use: "the CTDs at Southern Hydrate Ridge" found
  // no CTD record, "the CTD at" did.
  let q = String(question || "").replace(/\b([A-Z]{2,6})s\b/g, "$1").replace(/\b(ctd|adcp|bpr|auv|rov)s\b/gi, "$1");
  const extra = [namedDas(q)?.search];
  for (const x of SHORTHAND) {
    x.asked.lastIndex = 0;
    if (!x.asked.test(q) || x.unless?.test(q)) continue;
    if (x.replace) { x.asked.lastIndex = 0; q = q.replace(x.asked, x.search); } else extra.push(x.search);
  }
  const words = extra.filter(Boolean);
  return words.length ? `${q} ${words.join(" ")}` : q;
}

export const namedDas = (question) => DAS_PRODUCTS.find((p) => p.asked.test(String(question || "").toLowerCase())) ?? null;

// A question about the DAS experiments in general ("what DAS experiments were done here") names none of them, and
// the search for it found web pages and one paper (2021 whale calls) before the experiments' own records: the 2025–26
// experiment went unmentioned. Such a question gets each experiment's record (dasExperimentRecords in the Worker).
export const DAS_EXPERIMENTS = ["das21", "das24", "das25"].map((key) => DAS_PRODUCTS.find((p) => p.key === key));
export function isDasOverview(question) {
  const q = String(question || "").toLowerCase();
  return !namedDas(q) && /\b(?:das|distributed acoustic sensing)\b/.test(q)
    // The plural, or what was done: "from the 4-day DAS experiment, how many earthquakes" asks about one paper's results.
    && /\b(?:experiments|deployments|campaigns|datasets|done|conducted|carried out|history)\b/.test(q);
}

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
// What kind of source a hit is, so that where sources disagree the answer can prefer the scientific literature: the
// literature collection and its full-text layer, and any record cited by a DOI (the papers RCA Information carries).
export function sourceKind(hit) {
  const collection = String(hit.collection_id || "").toLowerCase();
  if (collection === "literature" || isLayer(hit) || hit.metadata?.source_row_type === "paper"
      || (hit.citations || []).some((c) => DOI_URL.test(c.url || ""))) return "scientific literature";
  if (collection === "websites") return "website";
  return null;
}

export function evidencePackage(hits, sourceNumbers) {
  const sections = [];
  // Full-text passages come last, in room of their own (eight passages of ~1,300 characters, the median page):
  // the main evidence and the passages never take each other's room.
  const room = { main: hits.some(isLayer) ? MAIN_WITH_FULLTEXT_CHARS : MAX_EVIDENCE_CHARS, layer: FULLTEXT_CHARS };
  for (const hit of hits) {
    const budget = isLayer(hit) ? "layer" : "main";
    if (room[budget] <= 0) continue;
    const refs = [...new Set((hit.citations || []).map((c) => sourceNumbers.get(sourceKey(c.source_id || hit.chunk_id, c.url))).filter(Boolean))];
    const kind = isLayer(hit) ? "scientific literature, full text" : sourceKind(hit);
    const header = `${hit.title}${kind ? ` (${kind})` : ""}${refs.length ? ` | sources: ${refs.map((n) => `[${n}]`).join(" ")}` : ""}\n`;
    const text = String(hit.text || "").slice(0, isLayer(hit) ? PASSAGE_CHARS : undefined).slice(0, Math.max(0, room[budget] - header.length));
    sections.push(`${header}${text}`);
    room[budget] -= header.length + text.length + 2;
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

// A calendar day as people write it: 2026-10-01, October 1 2026, Oct 1st, 1 October, 10/1/2026 (US order), with a
// slip in the ordinal ("1sr") allowed. Without a year it is the latest such day up to today. Null for none, or for a
// day that does not exist (February 30).
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
const MONTH = "(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\\.?";
const DAY = "(\\d{1,2})(?:st|nd|rd|th|[a-z]{1,2})?";
const YEAR = "(?:,?\\s*(20\\d{2}))?";
export function namedDay(question, today) {
  const q = String(question || "").toLowerCase();
  let y, m, d;
  let match = q.match(/\b(20\d{2})-(\d{1,2})-(\d{1,2})\b/);
  if (match) [, y, m, d] = match;
  else if ((match = q.match(new RegExp(`\\b${MONTH}\\s+${DAY}\\b${YEAR}`)))) { m = MONTHS.indexOf(match[1].slice(0, 3)) + 1; [, , d, y] = match; }
  else if ((match = q.match(new RegExp(`\\b${DAY}\\s+(?:of\\s+)?${MONTH}${YEAR}`)))) { m = MONTHS.indexOf(match[2].slice(0, 3)) + 1; [, d, , y] = match; }
  else if ((match = q.match(/\b(\d{1,2})\/(\d{1,2})(?:\/(20\d{2}))?\b/))) [, m, d, y] = match;
  else return null;
  const iso = (year) => `${year}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  let day = iso(y || today.slice(0, 4));
  if (!y && day > today) day = iso(Number(today.slice(0, 4)) - 1);
  const check = new Date(`${day}T00:00:00Z`);
  return Number.isNaN(check.getTime()) || check.toISOString().slice(0, 10) !== day ? null : day;
}

// The catalog's home page says how far its locations reach ("with locations up to 08-Oct-2026 11:00:00 UTC"). Later
// hours are not located yet (the site backfills them), so their daily files are empty: not quiet, uncounted.
export function locatedUntil(html) {
  const m = String(html || "").match(/locations up to\s+(\d{1,2})-([a-z]{3})-(\d{4})\s+(\d{2}):(\d{2}):(\d{2})\s*UTC/i);
  const month = m ? MONTHS.indexOf(m[2].toLowerCase()) : -1;
  return month < 0 ? null : new Date(Date.UTC(+m[3], month, +m[1], +m[4], +m[5], +m[6]));
}

// A magnitude floor in a count question: "above magnitude 2" (more than 2), "M2+", "magnitude 2.5 or larger",
// "at least M 3" (2.5 and 3 included). Null when the question sets none.
export function magnitudeFloor(question) {
  const q = String(question || "").toLowerCase();
  const strict = q.match(/\b(?:above|over|greater than|larger than|bigger than|more than|exceeding)\s+(?:an?\s+)?(?:magnitude|mag|mw?)\s*(-?\d+(?:\.\d+)?)/);
  if (strict) return { value: Number(strict[1]), inclusive: false };
  const inclusive = q.match(/\b(?:at least|minimum)\s+(?:an?\s+)?(?:magnitude|mag|mw?)\s*(-?\d+(?:\.\d+)?)/)
    || q.match(/\b(?:magnitude|mag|mw?)\s*(-?\d+(?:\.\d+)?)\s*(?:\+|or (?:above|more|greater|larger|bigger|higher))/)
    || q.match(/(?:≥|>=)\s*(?:magnitude|mag|mw?)?\s*(-?\d+(?:\.\d+)?)/);
  return inclusive ? { value: Number(inclusive[1]), inclusive: true } : null;
}

export function axialDayWindow(question, { tz, now = new Date() } = {}) {
  const q = String(question || "").toLowerCase();
  if (!/axial/.test(q) || !/(how many|count|number of)/.test(q) || !/earthquake/.test(q)) return null;
  const zone = tz ? validZone(tz) : "UTC", today = ymd(now, zone);
  const named = namedDay(q, today);
  let day;
  if (named) day = named;
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
  return { day, tz: zone, today: day === today, future: day > today, start: new Date(start), end: new Date(end), stamps, label, zoneName };
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

// "Is the pressure gauge at Slope Base operational?": a question about an instrument's current state, which the
// live monitor answers (the map card's own check) and no corpus record can.
export function isStatusQuestion(question) {
  return /\b(?:operational|operating|working|online|offline|running|functioning|status|down|broken|healthy|recording|transmitting|streaming)\b/
    .test(String(question || "").toLowerCase());
}
// OOI reference designators (RS01SLBS-MJ01A-06-PRESTA101, RS01SBPS-PC01A-4A-CTDPFA103, RS01SUM2-MJ01B-CTDPFA110), and
// the OO seismic stations EarthScope serves (AXEC1, HYSB1), which Nereus does not track: their waveform is checked.
// What a status question asks about, without the words that ask it: "Is the CTD at Southern Hydrate Ridge online?"
// ranked the CTD's record 48th, "the CTD at Southern Hydrate Ridge" 7th.
const STATUS_TERMS = /\b(?:is|are|was|were|it|they|still|currently|right now|now|operational|operating|working|online|offline|running|functioning|status|down|broken|healthy|recording|transmitting|streaming)\b/gi;
export const statusSearch = (question) => String(question || "").replace(STATUS_TERMS, " ").replace(/[?]/g, " ").replace(/\s+/g, " ").trim();

// The instrument types a status question can name, and the words their records use: only instruments of the type
// asked are checked live ("the CTD at Southern Hydrate Ridge" checks no ADCP). A question naming none checks all.
const INSTRUMENT_TYPES = [
  [/\bctds?\b|conductivity/i, /\bctd|conductivity/i], [/seismo|seismic station/i, /seismi/i], [/pressure|\bbpr|\bbotpt|tide gauge/i, /pressure|tidal|\bbotpt|\bprest/i],
  [/hydrophone/i, /hydrophone/i], [/\badcps?\b|current meter|currents/i, /\badcp|velocity|current/i], [/camera/i, /camera/i],
  [/fluorometer|chlorophyll|cdom/i, /fluorometer|chlorophyll|cdom/i], [/oxygen|\bdo\b/i, /oxygen|\bdosta|\bctd-do/i], [/tilt/i, /tilt/i],
  [/thermistor|temperature/i, /thermistor|temperature|\btmpsf/i], [/sonar|covis/i, /sonar|covis/i], [/\bph\b/i, /\bph\b|\bphsen/i],
  [/spectrometer|mass spec/i, /spectrometer/i], [/profiler/i, /profiler/i], [/\bdas\b|fiber|fibre/i, /\bdas\b|fiber|fibre|distributed acoustic/i],
];
export function askedType(question) {
  const q = String(question || "");
  return INSTRUMENT_TYPES.filter(([asked]) => asked.test(q)).map(([, record]) => record);
}

const REFDES = /\b[A-Z]{2}\d{2}[A-Z0-9]{4}-[A-Z0-9]{5}-(?:[A-Z0-9]{2}-)?[A-Z0-9]{9}\b/;
const STATION = /\b(?:AX[A-Z]{2}|HYS[A-Z0-9])\d\b/;
export const refdesOf = (hit) => `${hit.title || ""}\n${hit.text || ""}`.match(REFDES)?.[0] ?? null;
// One instrument's records under one name: its Arcada copies, OOI record and PI portal routing record.
export const instrumentKey = (title) => String(title || "").toLowerCase()
  .replace(/\s*\((?:description|params)\)$/, "").replace(/\s+data availability and routing$/, "").trim();
export function liveTargetOf(hit) {
  const refdes = refdesOf(hit);
  if (refdes) return { kind: "status", id: refdes };
  // A PI instrument record names its parts ("Canonical identifier: CTDPFA110", "OOI site RS01SUM2, node MJ01B").
  const text = `${hit.title || ""}\n${hit.text || ""}`;
  const id = text.match(/Canonical identifier:\s*([A-Z]{6}\d{3})\b|\/data\/([A-Z]{6}\d{3})\//)?.slice(1).find(Boolean), place = text.match(/OOI site ([A-Z]{2}\d{2}[A-Z0-9]{4}), node ([A-Z0-9]{5})\b/);
  if (id && place) return { kind: "status", id: `${place[1]}-${place[2]}-${id}` };
  const station = `${hit.title || ""}\n${hit.text || ""}`.match(STATION)?.[0];
  return station ? { kind: "waveform", id: `OO.${station}` } : null;
}
const STATUS_WORDS = { OPERATIONAL: "operating", PARTIALLY_FUNCTIONAL: "partially functional", NOT_DEPLOYED: "not deployed", RETIRED: "retired",
  SUPERSEDED: "superseded", RECOVERED: "recovered", UNCABLED: "uncabled", UNKNOWN: "of unknown status" };
const utcTime = (iso) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? null : `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`; };

// The evidence record for one instrument's live check, as the map card reads it: Nereus's status and latest data
// check, else (for an instrument Nereus does not track) the age of its newest data. It carries the instrument
// record's citations, so the answer cites, and the map pins, the instrument.
export function liveStatusHit(hit, refdes, live) {
  const name = String(hit.title || refdes).replace(/\s*\((?:description|params)\)$/i, "");
  let text;
  if (!live) text = `The live check of ${name} (${refdes}) could not be made just now; no current status is known.`;
  else if (live.kind === "waveform") {
    text = live.recording
      ? `${name} (${refdes}) is recording, checked live at EarthScope: its newest waveform (${live.channel}${live.rate ? `, ${live.rate} samples/s` : ""}) is from ${utcTime(live.latestMs) || "a recent time"}, ${live.delayMinutes ?? "?"} min behind real time.`
      : `${name} (${refdes}) has no recent waveform at EarthScope, checked live: ${live.message || "no recent data"}.`;
  }
  else if (live.untracked) text = `${name} (${refdes}) has no live status: the atlas's live monitor does not track it.`;
  else if (live.evidenceMode === "data_age") {
    text = `${name} (${refdes}) is not tracked by Nereus, the RCA's instrument monitor. Its newest data are from ${utcTime(live.latestAt) || "an unknown time"}`
      + `${live.basis === "erddap" ? " (OOI ERDDAP)" : " (its QA/QC plots)"}${live.status ? `, so it counts as ${STATUS_WORDS[live.status] || live.status}` : ""}.`;
  } else {
    const how = !live.evidenceMode || live.evidenceMode === "live" ? "checked live" : "from Nereus's last snapshot (the live check failed)";
    text = `${name} (${refdes}) is ${STATUS_WORDS[live.status] || "of unknown status"}, ${how} by Nereus, the RCA's instrument monitor`
      + `${live.data?.code ? `; its latest data check (${utcTime(live.data.checkedAt) || "time unknown"}) is ${live.data.code}` : ""}.`;
  }
  return { chunk_id: `LIVE-${refdes}`, collection_id: "live_status", title: `Live status: ${name}`, text, citations: hit.citations || [], live: true };
}

export function answerPrompt({ question, evidence, sources, mode, product = null }) {
  const liveInstruction = isStatusQuestion(question) && /^Live status: /m.test(evidence)
    ? "Records titled \"Live status\" were checked against the live monitor moments ago: say from them whether each instrument is operating now, with the time of its data check, ahead of any older or catalog status in other records."
    : "";
  const overviewInstruction = isDasOverview(question)
    ? `The RCA's DAS experiments are ${DAS_EXPERIMENTS.map((e) => e.about).join("; ")}. Count and describe these experiments, each once; a dataset within an experiment is part of it, not an experiment of its own.`
    : "";
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
  return `Retrieved RCA Atlas evidence:\n\n${evidence}\n\n---\nQuestion: ${question}\n\nRCA Atlas defaults to the OOI Regional Cabled Array and COSZO. Unless the user explicitly asks for a global comparison, answer in that scope and exclude tangential sites or literature outside it. First compare the individual named records in the evidence against the question. Then answer the user's exact question directly. Do not lead with a generic instrument definition when the user asks which instruments exist or where they are. ${compactInstruction} ${overviewInstruction} ${liveInstruction} ${formatInstruction} ${mode === "compact" ? "If a requested dataset is missing from the evidence, say so in one sentence." : "If the evidence leaves part of the question unanswered, say in one short closing section what is missing. When the evidence answers the question fully, add no such section and do not hedge a supported answer. A total, maximum, ranking or comparison over a period (a year, or since 2015) is complete only if the evidence covers every part of that period: when it covers some months of a year, give the figure for the months covered, name them, and say the others are missing; never present a partial sum as the total."} ${citationInstruction} Evidence headers mark scientific literature and websites. When sources disagree about a fact or number, give the scientific literature's value and cite it; a website, news post or blog that reports it differently does not override the paper. Answer each quantity the question asks for with the value a source states for that same quantity: do not substitute a related finding (a range where one effect is weak for the stated peak or best value, a total for a subset), and do not attach one study's sites, instruments or depths to another study. Do not invent live values or tool results. Evidence sources available to you: ${sourceListText}`;
}

// The map places a paper by the atlas sites its full text names most (the passage search returns them): they are
// added to the paper's hits, where the map looks for site names.
export function withPlaces(hits, passages) {
  const places = new Map();
  for (const p of passages || []) {
    const key = paperKey(p), names = p.metadata?.places;
    if (key && Array.isArray(names) && names.length && !places.has(key)) places.set(key, names);
  }
  return hits.map((hit) => {
    const names = places.get(paperKey(hit));
    return names ? { ...hit, metadata: { ...(hit.metadata || {}), places: names } } : hit;
  });
}

function runsOf(texts, n) {
  const runs = new Set();
  for (const text of texts) {
    const w = words(text);
    for (let i = 0; i + n <= w.length; i += 1) runs.add(w.slice(i, i + n).join(" "));
  }
  return runs;
}
const words = (text) => String(text || "").toLowerCase().replace(/[‐-–]/g, "-").replace(/[^a-z0-9 ]+/g, " ").split(/\s+/).filter(Boolean);
