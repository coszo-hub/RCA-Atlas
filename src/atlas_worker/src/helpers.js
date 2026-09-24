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

// The synthesis prompt. Sources are numbered in answer_citations order; the evidence headers carry the same
// numbers, and the model cites them as [n] so the interface can link each claim to its source (and its place).
export function answerPrompt({ question, evidence, sources, mode, product = null }) {
  const sourceListText = sources.map((c, i) => `[${i + 1}] ${c.title}`).join("; ");
  const namedProductInstruction = product
    ? `The user specifically named ${product}; answer only about that named product. Do not include related products, file formats, instruments, or data types unless the evidence explicitly assigns them to ${product}.`
    : "";
  const compactInstruction = mode === "compact"
    ? `This is a data-availability, download, or list question. ${namedProductInstruction} Return a direct answer followed by at most four single-sentence bullets; each bullet names one available dataset or route, with its year or coverage and file type only when established. Use no sub-bullets, section headings, capability descriptions, deployment background, calibration details, or related literature. Keep the whole answer under 120 words. The interface renders links separately.`
    : "Write a complete, useful research answer from the evidence, but do not pad it with loosely related instruments, background, or speculation. For an instrument inventory question, identify every matching named instrument record you can support, then describe its identity, site or location, capabilities or measurements, and where its data are available when the evidence provides that. Never infer that a sensor type is absent merely because it is not in a partial evidence set; say that the retrieved evidence is incomplete instead.";
  const formatInstruction = mode === "compact"
    ? "Use plain text, with no Markdown hashes or asterisks. Obey the 120-word, single-sentence-bullet limit exactly."
    : "Structure the response as plain text: a brief direct answer, then section labels on their own lines and hyphen bullets where there are multiple locations, instruments, or findings. Do not use Markdown hashes or asterisks.";
  const citationInstruction = "Cite the evidence with the bracketed source numbers [n] from the evidence headers (for example [2] or [1, 3]), placed directly after the claim they support. Use only those numbers. Do not include chunk IDs, source IDs, database identifiers, URLs, titles in brackets, or any other provenance notation in the answer text; the interface renders the numbered source list separately below the answer.";
  return `Retrieved RCA Atlas evidence:\n\n${evidence}\n\n---\nQuestion: ${question}\n\nRCA Atlas defaults to the OOI Regional Cabled Array and COSZO. Unless the user explicitly asks for a global comparison, answer in that scope and exclude tangential sites or literature outside it. First compare the individual named records in the evidence against the question. Then answer the user's exact question directly. Do not lead with a generic instrument definition when the user asks which instruments exist or where they are. ${compactInstruction} ${formatInstruction} State clearly what the evidence does not establish. ${citationInstruction} Do not invent live values or tool results. Evidence sources available to you: ${sourceListText}`;
}
