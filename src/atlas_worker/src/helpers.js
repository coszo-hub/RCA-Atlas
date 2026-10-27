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
// Download recipes (data/DataRecipes) have room of their own too: one instrument's runs to ~7,000 characters, and the
// site page and instrument records still lead the main evidence.
export const RECIPE_COLLECTION = "data_recipes";
const RECIPE_CHARS = 16_000;
const isRecipe = (hit) => hit.collection_id === RECIPE_COLLECTION;

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
// The words a search for papers keys on when the main search found none: numbers, names and long words
// ("2021 upwelling US Pacific Northwest"), at most six, OR'd. The main search's lexical half asks for every word of
// the question, which a long question rarely matches, so its vector half alone ranked web pages ("VISIONS'21 Live
// Video") above the paper; any six distinctive words find it, and more common words make the search too slow.
const QUESTION_WORDS = new Set(["a", "an", "and", "are", "at", "be", "between", "by", "did", "do", "does", "for", "from", "has", "have",
  "how", "in", "is", "it", "its", "of", "off", "on", "or", "than", "that", "the", "their", "there", "these", "this", "to", "was",
  "were", "what", "when", "where", "which", "who", "why", "with", "long", "many", "much", "about", "during", "since", "show"]);
export function distinctiveWords(question) {
  const words = (String(question || "").match(/[A-Za-z0-9][A-Za-z0-9-]*/g) || []).filter((w) => !QUESTION_WORDS.has(w.toLowerCase()));
  const first = words[0];
  const rank = (w) => (/\d/.test(w) ? 0 : /^[A-Z]/.test(w) && w !== first ? 1 : w.length >= 7 ? 2 : 3);
  return [...new Set(words.filter((w) => rank(w) < 3))].sort((a, b) => rank(a) - rank(b)).slice(0, 6);
}

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
  const room = { main: hits.some(isLayer) ? MAIN_WITH_FULLTEXT_CHARS : MAX_EVIDENCE_CHARS, layer: FULLTEXT_CHARS, recipe: RECIPE_CHARS };
  for (const hit of hits) {
    const budget = isLayer(hit) ? "layer" : isRecipe(hit) ? "recipe" : "main";
    if (room[budget] <= 0) continue;
    const refs = [...new Set((hit.citations || []).map((c) => sourceNumbers.get(sourceKey(c.source_id || hit.chunk_id, c.url))).filter(Boolean))];
    const kind = isLayer(hit) ? "scientific literature, full text" : isRecipe(hit) ? "download recipe" : sourceKind(hit);
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

// "Which CTD sensors are in the network?": one instrument type across the whole array. The search found web pages
// about the cruise CTD rosette and none of the 16 CTD records; such a question gets every record of the type
// (typeRecords in the Worker). A question naming a site is left to the inventory search, which keeps to the site.
const SPECIFIC_PLACE = /southern hydrate ridge|hydrate ridge|axial|caldera|ashes|international district|oregon shelf|oregon offshore|slope base|summit|mid slope|endurance|newport|\bshr\b|\bosb\b/i;
const TYPE_SEARCH = ["CTD", "seismometer seismic station", "pressure", "hydrophone", "ADCP current", "camera", "fluorometer", "oxygen",
  "tilt", "temperature", "sonar", "pH", "spectrometer", "profiler", null];   // in INSTRUMENT_TYPES order; DAS has its own (isDasOverview)
export function typeInventory(question) {
  const q = String(question || "");
  if (SPECIFIC_PLACE.test(q) || isDasOverview(q)) return null;
  // The type is what the listing asks for, within a few words of it: "which CTD sensors", "how many pressure sensors",
  // "list all the hydrophones"; not "which fault drains the overpressured reservoir".
  // The type is counted as instruments: plural ("seismometers") or followed by "sensors", "gauges"…; not "what
  // temperature", "what depths were the hydrophones", "papers used COVIS data".
  const listed = (asked) => new RegExp(`\\b(?:which|what|list|all|every|how many|where are)\\W+(?:[\\w-]+\\W+){0,2}?(?:${asked.source})[\\w-]*?(?:s\\b|\\s+(?:sensors?|instruments?|gauges?|stations?|recorders?|meters?|probes?|packages?|devices?)\\b)`, "i").test(q);
  const i = INSTRUMENT_TYPES.findIndex(([asked]) => listed(asked));
  return i >= 0 && TYPE_SEARCH[i] ? { search: `${TYPE_SEARCH[i]} instrument`, record: INSTRUMENT_TYPES[i][1] } : null;
}

// "What is the serial number of the SCPR?", "when was the BOTPT last recovered?", "what was deployed on Visions 25?",
// "which instruments are deeper than 2500 m?": OOI asset-management metadata (the ooi_asset_management collection).
// Its records are a few hundred among 22,000, so the main search ranks web pages about the same instrument above
// them; such a question also searches that collection (assetRecords in the Worker).
const ASSET_WORDS = /\b(?:serial|s\/n|firmware|calibrat\w*|coefficients?|deploy\w*|redeploy\w*|recover\w*|cruises?|visions|manufactur\w*|make and model|(?:what|which)\s+(?:model|make)|who makes|made by|deeper|deepest|how deep|shallower|shallowest|junction box(?:es)?|j-?box(?:es)?|timeline|history|changes?|changed|swapp?\w*|replaced)\b/i;
// Makes and models ask the same records: "which CTDs are Sea-Bird SBE 16plus?".
const MAKERS = /\b(?:sea-?bird|sbe\s?\d+\w*|teledyne|rdi|aanderaa|nortek|sunburst|satlantic|wet ?labs|g[uü]ralp|paroscientific|nobska|kongsberg|simrad|hti|benthos|sonardyne|imagenex|nanometrics|turner)\b/i;
export const isAssetQuestion = (question) => ASSET_WORDS.test(String(question || "")) || MAKERS.test(String(question || ""));

// The asset-management chunks a question needs, by id, from the directory the asset builder writes
// (asset_directory.json): the named instrument's record (and its calibrations when asked), else the record of every
// instrument of the named type, a site's deployment counts, a year's cruises, the depth bands asked about.
// The RCA's places as questions name them, and the asset-management sites (TOC_L2) each one means.
const ASSET_PLACES = [
  [/\baxial (?:seamount )?base\b/i, /^Axial Base/], [/\bcentral caldera\b/i, /^Central Caldera/],
  [/\beast(?:ern)? caldera\b/i, /^Eastern Caldera/], [/\bashes\b/i, /^ASHES/],
  [/\binternational district (?:vent field )?1\b|\bint1\b/i, /^International District Vent Field 1/],
  [/\binternational district (?:vent field )?2\b|\bint2\b/i, /^International District Vent Field 2/],
  [/\binternational district\b(?!\s*(?:vent field\s*)?[12])/i, /^International District/],
  [/\bslope base\b|\bosb\b/i, /^Oregon Slope Base/], [/\bsouthern hydrate\b|\bhydrate ridge\b|\bhydrate summit\b|\bshr\b/i, /^Southern Hydrate/],
  [/\boregon offshore\b|\boffshore\b/i, /^Oregon Offshore/], [/\boregon shelf\b|\bshelf\b/i, /^Oregon Shelf/],
  [/\baxial\b/i, /^(?:Axial|Central Caldera|Eastern Caldera|ASHES|International District)/],
];
// Within a place, the platform a question names.
const ASSET_PLATFORMS = [[/\bshallow profiler\b|\b200 m platform\b/i, /Shallow Profiler/], [/\bdeep profiler\b/i, /Deep Profiler/],
  [/\bseafloor\b|\bbenthic\b/i, /Seafloor|Benthic|Caldera|ASHES|International District/]];
// Instrument words and the asset-management instrument types (vocab "Instrument") they mean.
const ASSET_TYPES = [
  [/\bctds?\b/i, /^CTD$/], [/\badcps?\b|\bcurrent profilers?\b|\bvelocity profilers?\b/i, /ADCP|Velocity Profiler/],
  [/\bbotpts?\b|\bbpts?\b|bottom pressure and tilt|\btilt\b/i, /^Bottom Pressure and Tilt$/],
  [/\bscprs?\b|self[- ]calibrating pressure/i, /^Self-Calibrating Pressure Recorder$/],
  [/\baccelerometers?\b|\bscta\b/i, /Accelerometer/], [/\ba-0-a\b|\ba0a\b/i, /^A-0-A/],
  [/broadband hydrophones?/i, /^Broadband Acoustic Receiver/], [/low[- ]frequency hydrophones?/i, /^Low Frequency Acoustic Receiver/],
  [/\bhydrophones?\b/i, /Hydrophone/], [/broadband (?:ocean bottom )?seismometers?|\bobsbb\b/i, /^Broadband Ocean Bottom Seismometer$/],
  [/short[- ]period (?:ocean bottom )?seismometers?|\bobssp\b/i, /^Short-Period Ocean Bottom Seismometer$/],
  [/\bseismometers?\b|\bobs\b/i, /Seismometer/], [/\boxygen\b|\boptodes?\b|\bdosta\b/i, /^Dissolved Oxygen$/],
  [/\bph\b/i, /pH/], [/\bpco2\b/i, /pCO2/], [/fluorometers?|chlorophyll|\bcdom\b/i, /Fluorometer/],
  [/\bhd (?:video )?camera\b|\bcamhd\b/i, /^HD Digital Video Camera$/], [/\bcameras?\b/i, /Camera/],
  [/\bcovis\b|vent imaging sonar/i, /^Vent Imaging Sonar$/], [/\bsonars?\b|echosounders?/i, /Sonar/],
  [/\b(?:tidal |tide )?pressure (?:sensors?|gauges?)\b|\bprest\b/i, /^Tidal Seafloor Pressure$|^A-0-A Pressure Sensor$/],
  [/temperature arrays?|\btmpsf\b|diffuse vent/i, /Temperature Array/], [/\btemperature sensors?\b/i, /^Temperature Sensor$/],
  [/spectrophotometers?|\boptaa\b|\bac-s\b/i, /^Spectrophotometer$/], [/mass spectrometers?/i, /^Mass Spectrometer$/],
  [/current meters?|velocity meters?|\bvel3d\b/i, /3-D Single Point Velocity Meter/], [/\bhpies\b|inverted echo/i, /Inverted Echo Sounder/],
  [/osmo\w*/i, /^Osmosis-Based Water Sampler$/], [/dna sampler|\bppsdn\b/i, /DNA Sampler/],
  [/transponders?|\bfetch\b/i, /^Acoustic Transponders$/], [/\btrhph\b|resistivity/i, /Temperature and Resistivity/],
  [/\bthsph\b|in[- ]situ chemistry|vent fluid chemistry/i, /In-situ Chemistry/], [/\brasfl\b|interactive sampler|fluid sampler/i, /Interactive Sampler/],
  [/benthic fluid flow|\bflobn\b/i, /^Benthic Fluid Flow$/], [/\bprofilers?\b(?!\s+\w*\s*(?:ctd|oxygen|fluorometer|ph|par))/i, /^Profiler vehicle/],
];
const CALIBRATION_WORDS = /\bcalibrat\w*|\bcoefficients?\b/i;
// A node a question names: its code (LJ03A, MJ03F, PC03A, SF03A, DP03A, PN03B) or a junction box at a place.
const NODE_CODE = /\b(?:LJ|MJ|LV|PN|PC|SF|DP)\d{2}[A-Z]\b/gi;
const NODE_WORDS = /\bjunction box(?:es)?\b|\bj-?box(?:es)?\b|\bnodes?\b/i;
const CRUISE_WORDS = /\bcruises?\b|\bvisions\b|\bexpeditions?\b|\b(?:deployed|recovered|installed) (?:on|during|in)\b/i;
const SITE_COUNT_WORDS = /\b(?:most|often|how many (?:times|deployments)|number of deployments|redeploy\w*)\b/i;
const MAX_ASSET_CHUNKS = 6;

// A question about getting data ("how do I download data from the shallow profiler at Slope Base?"); a named DAS
// dataset has its own download routes (namedDas).
export function isDataAccessQuestion(question) {
  const q = String(question || "");
  // Or a request for code ("a Python script for the Axial Base CTD temperature in March 2025"), which may name no data.
  return ((/\b(?:download|access|get|retrieve|obtain|fetch)\b/i.test(q)
    && /\b(?:data|datasets?|files?|recordings?|time series|waveforms?|images?|videos?)\b/i.test(q))
    || /\b(?:scripts?|code|python|matlab)\b/i.test(q)) && !namedDas(q);
}

// The OOI sites ("RS01SBPS") whose data a question asks for: those of the instruments at the place and platform it
// names, of the type it names when it names one. A place with no platform named is its seafloor site when it has
// one, as for asset questions ("the Axial Base CTD"). At most three.
// The instruments a data access question points at: those at the place, platform, node (MJ03F) or site code
// (RS03CCAL) it names, of the type it names if any, else of the OOI classes its words name ("pressure" is the bottom
// pressure and tilt, A-0-A and SCPR); a place alone means its seafloor instruments, not its moorings' profilers.
// typed says a type was named.
function accessInstruments(question, directory) {
  const q = String(question || "");
  const places = ASSET_PLACES.find(([asked]) => asked.test(q));
  const platform = ASSET_PLATFORMS.find(([asked]) => asked.test(q));
  const nodes = new Set((q.match(NODE_CODE) || []).map((code) => code.toUpperCase()));
  const sites = new Set((q.match(/\b(?:RS|CE)\d{2}[A-Z0-9]{4}\b/gi) || []).map((code) => code.toUpperCase()));
  if (!directory || (!places && !platform && !nodes.size && !sites.size)) return { instruments: [], typed: false };
  let instruments = directory.instruments.filter((i) => (!places || places[1].test(i.site)) && (!platform || platform[1].test(i.site))
    && (!nodes.size || nodes.has(i.refdes.split("-")[1])) && (!sites.size || sites.has(i.refdes.split("-")[0])));
  const types = ASSET_TYPES.filter(([asked]) => asked.test(q)).map(([, type]) => type);
  // The question's own words, less those naming the place or platform ("shallow profiler" is no "Velocity Profiler").
  const rest = [places, platform].reduce((text, found) => (found ? text.replace(new RegExp(found[0].source, "gi"), " ") : text), q);
  const words = (rest.toLowerCase().match(/\b[a-z]{5,}\b/g) || []).filter((w) => !/^(?:download|access|retrieve|obtain|where|which|there|profilers?|platforms?|moorings?|seafloor|script|python|between)$/.test(w));
  const matched = (i) => words.filter((w) => new RegExp(`\\b${w}\\b`, "i").test(i.instrument)).length;
  let typed = instruments.filter((i) => types.some((type) => type.test(i.instrument)));
  if (!typed.length) typed = instruments.filter((i) => matched(i) > 0);
  // The classes that match most of its words: "bottom pressure" is the Bottom Pressure and Tilt, not the Ocean Bottom
  // Seismometer; "broadband hydrophone" is not the low-frequency one.
  const best = Math.max(0, ...typed.map(matched));
  if (best > 0) typed = typed.filter((i) => matched(i) === best);
  if (typed.length) instruments = typed;
  if (places && !platform && !nodes.size) { const fixed = instruments.filter((i) => !/Profiler/.test(i.site)); if (fixed.length) instruments = fixed; }
  return { instruments, typed: typed.length > 0 };
}

// Every instrument of the type a data access question names when it names no place, platform, node or site ("how do I
// download oxygen sensor data?"): the type's overview recipe lists them all, where each is and its easiest route.
export function typeOnlyInstruments(question, directory) {
  const q = String(question || "");
  if (!directory || ASSET_PLACES.some(([asked]) => asked.test(q)) || ASSET_PLATFORMS.some(([asked]) => asked.test(q))
      || (q.match(NODE_CODE) || []).length || /\b(?:RS|CE)\d{2}[A-Z0-9]{4}\b/i.test(q)) return [];
  const types = ASSET_TYPES.filter(([asked]) => asked.test(q)).map(([, type]) => type);
  if (types.length) return directory.instruments.filter((i) => types.some((type) => type.test(i.instrument))).map((i) => i.refdes);
  // Else the classes that match most of its words ("pressure" is the BOTPT, the tidal gauges, the HPIES, A-0-A and SCPR).
  const words = (q.toLowerCase().match(/\b[a-z]{5,}\b/g) || []).filter((w) => !/^(?:download\w*|access|retrieve|obtain|where|which|there|sensors?|instruments?|datasets?|files|script|python|between|could|would|about|their)$/.test(w));
  const matched = (i) => words.filter((w) => new RegExp(`\\b${w}\\b`, "i").test(i.instrument)).length;
  const best = Math.max(0, ...directory.instruments.map(matched));
  return best ? directory.instruments.filter((i) => matched(i) === best).map((i) => i.refdes) : [];
}

export function dataAccessSites(question, directory) {
  return [...new Set(accessInstruments(question, directory).instruments.map((i) => i.refdes.slice(0, 8)))].slice(0, 3);
}

// The reference designators of the instrument type a data access question names at its site ("the CTD on the 200 m
// platform at Axial Base"): every one of them, so the records' Mounted on lines tell the user which is which.
export function dataAccessInstruments(question, directory) {
  const { instruments, typed } = accessInstruments(question, directory);
  return typed ? instruments.map((i) => i.refdes).slice(0, 4) : [];
}

export function assetChunkIds(question, directory) {
  const q = String(question || "");
  if (!directory || !isAssetQuestion(q)) return [];
  const places = ASSET_PLACES.find(([asked]) => asked.test(q));
  const platform = ASSET_PLATFORMS.find(([asked]) => asked.test(q));
  const atPlace = (site) => (!places || places[1].test(site)) && (!platform || platform[1].test(site));
  // The most specific type a question names: "the CAMHD camera" is the HD video camera, not every camera; and
  // "profiler" is the profiler vehicle only when no instrument on it is named ("the deep profiler VEL3D").
  const family = (type) => (/Camera/.test(type.source) ? "camera" : /Hydrophone|Acoustic Receiver/.test(type.source) ? "hydrophone"
    : /Seismometer/.test(type.source) ? "seismometer" : /Sonar/.test(type.source) ? "sonar" : null);
  const types = [], families = new Set();
  for (const [asked, type] of ASSET_TYPES) {
    if (!asked.test(q) || (family(type) && families.has(family(type)))) continue;
    if (/Profiler vehicle/.test(type.source) && types.length) continue;
    types.push(type);
    if (family(type)) families.add(family(type));
  }
  const codesNamed = [...q.matchAll(/\b([A-Z][A-Z0-9]{3,4})s?\b/g)].map((m) => m[1]);
  if (codesNamed.length && types.length > 1) {
    // A code names its type outright ("VEL3D", "CAMHD"): keep the types its instruments have.
    const byCode = directory.instruments.filter((i) => i.codes.some((c) => codesNamed.includes(c))).map((i) => i.instrument);
    const kept = types.filter((type) => byCode.some((name) => type.test(name)));
    if (kept.length) types.splice(0, types.length, ...kept);
  }
  const named = new Set(q.match(new RegExp(REFDES_SOURCE, "g")) || []);
  // Codes as written, plural too ("VEL3Ds", "CTDs").
  const codes = new Set([...q.matchAll(/\b([A-Z][A-Z0-9]{3,4})s?\b/g)].map((m) => m[1]));
  const ofType = (i) => types.some((type) => type.test(i.instrument)) || i.codes.some((code) => codes.has(code));
  let instruments = directory.instruments.filter((i) => named.has(i.refdes));
  if (!instruments.length && (types.length || codes.size)) instruments = directory.instruments.filter((i) => ofType(i) && atPlace(i.site));
  // "The Axial Base CTD", with no platform named, is the seafloor one when there is one; the profilers' CTDs are
  // asked for as the shallow or deep profiler's.
  if (places && !platform && instruments.length > 1) {
    const fixed = instruments.filter((i) => !/Profiler/.test(i.site));
    if (fixed.length) instruments = fixed;
  }
  const ids = [];
  if (instruments.length && instruments.length <= 3) {
    for (const i of instruments) {
      ids.push(`ooi_assets_${i.refdes}`);
      if (i.calibration && CALIBRATION_WORDS.test(q)) ids.push(`ooi_assets_calibration_${i.refdes}`);
      ids.push(...(i.sourced || []));   // its components' serial numbers from papers and pages, each cited to its source
    }
  } else if (instruments.length && places) {
    // Several at a named place ("the Axial Base ADCP": the seafloor and both profiler ones): each one's record.
    ids.push(...instruments.map((i) => `ooi_assets_${i.refdes}`));
  } else if (instruments.length) {
    // A type across the network ("which CTDs are SBE 16plusV2?"): the record of every instance of each type.
    ids.push(...[...new Set(instruments.map((i) => directory.types[i.instrument]).filter(Boolean))].slice(0, 3));
  }
  const nodeCodes = new Set((q.match(NODE_CODE) || []).map((code) => code.toUpperCase()));
  if (directory.nodes && (nodeCodes.size || (places && NODE_WORDS.test(q) && !instruments.length))) {
    for (const [node, entry] of Object.entries(directory.nodes)) {
      const code = node.split("-")[1];
      if ((nodeCodes.size ? nodeCodes.has(code) : /^(?:LJ|MJ)/.test(code)) && atPlace(entry.site)) ids.push(entry.id, ...(entry.sourced || []));
    }
  }
  if (places && !instruments.length && !nodeCodes.size && SITE_COUNT_WORDS.test(q)) {
    ids.push(...Object.entries(directory.sites).filter(([site]) => atPlace(site)).map(([, id]) => id));
  }
  if (CRUISE_WORDS.test(q)) {
    const years = [...q.matchAll(/\b(20\d\d)\b/g)].map((m) => m[1])
      .concat([...q.matchAll(/\bvisions\s*['’]?\s*(\d\d)\b/gi)].map((m) => `20${m[1]}`));
    ids.push(...[...new Set(years)].map((year) => directory.cruise_years[year]).filter(Boolean));
  }
  if (!instruments.length || instruments.length > 3) {
    const deeper = q.match(/\b(?:deeper|below|more) than\s+(\d[\d,]*)/i), shallower = q.match(/\b(?:shallower|less) than\s+(\d[\d,]*)/i);
    const overlaps = (band, low, high) => (band.high == null || band.high > low) && (band.low == null || band.low < high);
    let bands = [];
    if (deeper) bands = directory.depth_bands.filter((b) => overlaps(b, Number(deeper[1].replace(/,/g, "")), Infinity));
    else if (shallower) bands = directory.depth_bands.filter((b) => overlaps(b, -Infinity, Number(shallower[1].replace(/,/g, ""))));
    else if (/\bdeepest\b/i.test(q)) bands = directory.depth_bands.slice(0, 1);
    else if (/\bshallowest\b/i.test(q)) bands = directory.depth_bands.slice(-1);
    ids.push(...bands.map((b) => b.id));
  }
  return [...new Set(ids)].slice(0, MAX_ASSET_CHUNKS);
}

// "What papers used AXEC1 and AXEC2?", "which studies used the Slope Base pressure gauge?": papers that used a sensor.
// No abstract names a sensor; the papers' full text does (by station code, reference designator or instrument code)
// or describes it in words. Such a question asks the whole full-text layer (papersFor in the Worker).
const PAPER_WORDS = /\b(?:papers?|studies|study|publications?|articles?|literature|research)\b/i;
const USE_WORDS = /\b(?:us(?:e|es|ed|ing)|cit(?:e|es|ed|ing)|mention(?:s|ed)?|based on|analy[sz](?:e|es|ed)|data from|relied|employ(?:s|ed)?|record(?:s|ed)?)\b/i;
// It asks for papers ("which papers used…", "what studies used…", "papers that mention…"), not about one study's
// methods ("which echosounder was used… in the 2016 study").
const ASKS_FOR_PAPERS = /\b(?:which|what|list|any|find|show|name)\s+(?:[\w-]+\s+){0,2}(?:papers?|studies|publications?|articles?)\b|\b(?:papers?|studies|publications?|articles?)\s+(?:that|which|have|has)\b/i;
export const isPaperUsageQuestion = (question) => ASKS_FOR_PAPERS.test(String(question || "")) && USE_WORDS.test(String(question || ""));
export const instrumentSearch = (question) => String(question || "").replace(PAPER_WORDS, " ").replace(USE_WORDS, " ")
  .replace(/\b(?:what|which|have|has|had|the|that|any|did|do|does|data|of)\b/gi, " ").replace(/[?]/g, " ").replace(/\s+/g, " ").trim();
// The codes a paper names an instrument by: its station code (AXEC2), reference designator and that designator's
// instrument code (CTDPFB304), from the codes in the question and the instrument records found for it.
// The place a paper-usage question names ("Slope Base" in "the Slope Base pressure gauge"): its instrument words without
// the type and generic words. A passage found by meaning must name it, or it is about another gauge.
// The codes a question gives: station codes and designators, and acronyms in capitals (BOTPT, COVIS, MARUM) that
// papers write as the instrument's name; not the project's own (OOI, RCA, COSZO, NSF).
const NOT_INSTRUMENTS = new Set(["OOI", "RCA", "COSZO", "NSF", "UTC", "USA", "NOAA", "IRIS", "DAS"]);
export function questionCodes(question) {
  const acronyms = String(question || "").match(/\b[A-Z][A-Z0-9]{3,9}\b/g) || [];
  return [...new Set([...instrumentCodes([question]), ...acronyms.filter((a) => !NOT_INSTRUMENTS.has(a))])].slice(0, 6);
}
export function askedPlace(question) {
  let q = instrumentSearch(question);
  for (const [asked] of INSTRUMENT_TYPES) q = q.replace(new RegExp(asked.source, "gi"), " ");
  for (const code of questionCodes(q)) q = q.replace(code, " ");
  return q.replace(/\b(?:sensors?|gauges?|instruments?|recorders?|stations?|from|and|at|on|in)\b/gi, " ").replace(/\s+/g, " ").trim();
}
export function instrumentCodes(texts) {
  const codes = new Set();
  for (const text of texts) {
    const t = String(text || "");
    for (const m of t.matchAll(/\bEARTHSCOPE-OO-([A-Z0-9]{5})\b/g)) codes.add(m[1]);
    // A reference designator, its instrument code (CTDPFB304) and its node (MJ01A, the Slope Base node papers name).
    for (const m of t.matchAll(new RegExp(REFDES_SOURCE, "g"))) { codes.add(m[0]); codes.add(m[0].split("-").at(-1)); codes.add(m[0].split("-")[1]); }
    for (const m of t.matchAll(/\bCanonical identifier:\s*([A-Z]{6}\d{3})\b/g)) codes.add(m[1]);
    for (const m of t.matchAll(new RegExp(STATION_SOURCE, "g"))) codes.add(m[0]);
    // An acronym in a record's title, as papers write it: "Cabled Observatory Vent Imaging Sonar (COVIS)".
    for (const m of t.split("\n")[0].matchAll(/\(([A-Z][A-Z0-9-]{2,11})\)/g)) codes.add(m[1]);
  }
  return [...codes].slice(0, 6);
}

const REFDES_SOURCE = "\\b[A-Z]{2}\\d{2}[A-Z0-9]{4}-[A-Z0-9]{5}-(?:[A-Z0-9]{2}-)?[A-Z0-9]{9}\\b";
const STATION_SOURCE = "\\b(?:AX[A-Z]{2}|HYS[A-Z0-9])\\d\\b";
const REFDES = new RegExp(REFDES_SOURCE);
const STATION = new RegExp(STATION_SOURCE);
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

export function answerPrompt({ question, evidence, sources, mode, product = null, access = false }) {
  const recipes = /\(download recipe\) \| sources:/.test(evidence);
  const typeOverview = /^Where to download .* data: every .* \(download recipe\) \| sources:/m.test(evidence);
  const liveInstruction = isStatusQuestion(question) && /^Live status: /m.test(evidence)
    ? "Records titled \"Live status\" were checked against the live monitor moments ago: say from them whether each instrument is operating now, with the time of its data check, ahead of any older or catalog status in other records."
    : "";
  const papersInstruction = isPaperUsageQuestion(question)
    ? "The question asks which papers used an instrument. Full-text passages from papers that name it or describe it are in the evidence. List each paper whose passage shows it used or analyzed that instrument's data, by title with its citation and a few words on how it used it; list papers that only mention the instrument separately as mentions; leave out papers whose passages are about something else."
    : "";
  const overviewInstruction = isDasOverview(question)
    ? `The RCA's DAS experiments are ${DAS_EXPERIMENTS.map((e) => e.about).join("; ")}. Count and describe these experiments, each once; a dataset within an experiment is part of it, not an experiment of its own.`
    : "";
  const sourceListText = sources.map((c, i) => `[${i + 1}] ${c.title}`).join("; ");
  const namedProductInstruction = product
    ? `The user specifically named ${product}; answer only about it. Do not include other experiments, routes, file formats, instruments, or data types unless the evidence assigns them to it.`
    : "";
  // How to get a platform's data: its site page leads, then only the OOI routes that serve that kind of data.
  const accessInstruction = access
    ? "The question asks how to get an OOI platform's or instrument's data. Lead with the platform's own site page: its Data Access links (the data on the platform and its subcomponents in Data Explorer) and its DOI for citing the data. When the platform has parts, such as a shallow profiler mooring's moving shallow profiler and fixed 200 m platform, name each part with the code this platform's own records give it (the site page and the instrument records' Mounted on lines; codes differ between sites) and the asked instruments on it, citing those records, so the user knows which part's data to open. Then give at most three other routes from the Data Access and M2M pages that serve this kind of instrument data (such as ERDDAP, THREDDS or the M2M API, with an M2M example for this platform if the evidence has one; for seismometer or hydrophone data, IRIS first, where the Data Access page says the RCA's seismic and hydrophone data are deposited), one line each. Leave out routes for other data, such as cruise data, community datasets, water samples, imagery and partner sites. Do not list the instrument records one by one."
    : "";
  // A download recipe: the easiest route for what was asked, then a script for this dataset and timeframe from the
  // recipe's tested code, changing only the timeframe and variables.
  const recipeInstruction = recipes
    ? "Records marked (download recipe) give, for one instrument, its tested routes to the data, easiest first, each with a Python script. Answer with the route that best fits what was asked: the one marked Easiest unless the question wants something it does not give (every sample or a variable only another route has; the original files; waveforms). Say in one sentence why that route. Then write one complete Python script for the asked instrument, variables and timeframe, in a single ```python fenced block: copy that route's script from the recipe and change only its START and END (and its VARIABLES or e.variables to the asked ones, using only variable names the recipe lists). Times are UTC; when the question gives no timeframe, use the last day before the recipe's coverage ends and say so. Never invent a dataset ID, stream, variable, URL or file name the recipe does not give, and never put a password, username or token in a script. After the script, one line each for at most two other routes the recipe gives. Cite the recipe. "
    + (typeOverview ? "The question names no place, and the record headed Where to download ... data: every ... lists every instrument of that type. Begin by saying how many there are and, in one hyphen bullet each, where each one is and what it is on (seafloor, the 200 m platform, or a profiler), with its dataset ID or other easiest route, as that record gives them. Then give the script from the example recipe for its instrument, saying which instrument it is for, and say in one sentence that for another instrument the script changes only the dataset ID (and the variable names, which that instrument's own recipe lists). Ask no question back. " : "")
    : "";
  const compactInstruction = recipes ? recipeInstruction : access ? accessInstruction : mode === "compact"
    ? `This is a data-availability, download, or list question. ${namedProductInstruction} Give a one-sentence direct answer. Then, for each dataset or experiment, one plain line naming it by its source's title, with its years, coverage and file formats, cited with its source number; when one dataset has several numbered sources (download routes), add one hyphen bullet per source, giving its name and only what the evidence ties to that source itself. Sub-folders that the evidence names inside one source (such as the 2021 dataset's OptaSense and Silixa folders) are described in one bullet of that dataset, not bullets of their own. Add one bullet for the folder layout or a caveat (such as very many files per day) when the evidence gives one. Include every numbered download source; never drop one. Leave out evidence that is not a downloadable dataset (papers, methods, policies) entirely, without remarking on it. Use no capability descriptions, deployment background, or calibration details. Keep the whole answer under 230 words. The interface links each cited source.`
    : "Write a complete, useful research answer from the evidence, but do not pad it with loosely related instruments, background, or speculation. For an instrument inventory question, identify every matching named instrument record you can support, then describe its identity, site or location, capabilities or measurements, and where its data are available when the evidence provides that. Never infer that a sensor type is absent merely because it is not in a partial evidence set; say that the retrieved evidence is incomplete instead.";
  const formatInstruction = recipes
    ? `Use plain text outside the one \`\`\`python block, with no Markdown headings or asterisks. Keep the words outside the script under ${typeOverview ? 400 : 150}.`
    : mode === "compact"
    ? "Use plain text, with no Markdown hashes or asterisks, and no URLs. Obey the 230-word limit."
    : "Structure the response as plain text: a brief direct answer, then section labels on their own lines and hyphen bullets where there are multiple locations, instruments, or findings. Do not use Markdown hashes or asterisks.";
  const citationInstruction = "Cite the evidence with the bracketed source numbers [n] from the evidence headers (for example [2] or [1, 3]), placed directly after the claim they support. Use only those numbers. Do not include chunk IDs, source IDs, database identifiers, URLs, titles in brackets, or any other provenance notation in the answer text; the interface renders the numbered source list separately below the answer.";
  return `Retrieved RCA Atlas evidence:\n\n${evidence}\n\n---\nQuestion: ${question}\n\nRCA Atlas defaults to the OOI Regional Cabled Array and COSZO. Unless the user explicitly asks for a global comparison, answer in that scope and exclude tangential sites or literature outside it. First compare the individual named records in the evidence against the question. Then answer the user's exact question directly. Do not lead with a generic instrument definition when the user asks which instruments exist or where they are. ${compactInstruction} ${overviewInstruction} ${liveInstruction} ${papersInstruction} ${formatInstruction} ${mode === "compact" ? "If a requested dataset is missing from the evidence, say so in one sentence." : "If the evidence leaves part of the question unanswered, say in one short closing section what is missing. When the evidence answers the question fully, add no such section and do not hedge a supported answer. A total, maximum, ranking or comparison over a period (a year, or since 2015) is complete only if the evidence covers every part of that period: when it covers some months of a year, give the figure for the months covered, name them, and say the others are missing; never present a partial sum as the total."} ${citationInstruction} Evidence headers mark scientific literature and websites. When sources disagree about a fact or number, give the scientific literature's value and cite it; a website, news post or blog that reports it differently does not override the paper. Answer each quantity the question asks for with the value a source states for that same quantity: do not substitute a related finding (a range where one effect is weak for the stated peak or best value, a total for a subset), and do not attach one study's sites, instruments or depths to another study. Do not invent live values or tool results. Evidence sources available to you: ${sourceListText}`;
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
