// Private Graph-RAG evidence -> Gemini synthesis boundary for RCA Atlas.
// Browser requests contain only a question. The Worker fetches evidence itself
// and returns stable corpus citations, never a Gemini key or Graph-RAG API key.

const MAX_QUERY_LENGTH = 1_000;
const MAX_HITS = 10;
const MAX_GRAPH_HOPS = 2;
const MAX_EVIDENCE_CHARS = 18_000;
const AXIAL_CATALOG = "http://axial.ocean.washington.edu";

function corsHeaders(env, origin) {
  const allowed = env.ALLOWED_ORIGIN || "https://coszo.org";
  const allow = origin === allowed ? origin : allowed;
  return {
    "access-control-allow-origin": allow,
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "content-type",
    "access-control-max-age": "86400",
    vary: "origin",
  };
}

function response(data, status, cors) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...cors, "content-type": "application/json", "cache-control": "no-store" },
  });
}

async function readJson(request) {
  try { return await request.json(); } catch { return null; }
}

function validOrigin(origin, env) {
  return origin === (env.ALLOWED_ORIGIN || "https://coszo.org");
}

function publicHit(hit) {
  return {
    chunk_id: hit.chunk_id,
    collection_id: hit.collection_id,
    collection_label: hit.collection_label,
    title: hit.title,
    score: hit.score,
    citations: hit.citations || [],
    metadata: hit.metadata || {},
  };
}

function citations(hits) {
  const known = new Set();
  return hits.flatMap((hit) => (hit.citations || []).map((citation) => ({
    id: citation.source_id || hit.chunk_id,
    // The PI portal importer preserves a shared corpus title for provenance,
    // but visitors need the dataset-specific route name beside the actual URL.
    title: /\/das25\/data\/multidas\/?$/i.test(citation.url || "")
      ? "DAS25 MultiDAS"
      : (/\/das25\/data\/optodas\/?$/i.test(citation.url || "")
        ? "DAS25 OptoDAS"
        : (/shared rca and coszo instruments corpus/i.test(citation.title || "")
          ? hit.title
          : (citation.title || hit.title))),
    url: citation.url || "",
  }))).filter((citation) => {
    const key = `${citation.id}|${citation.url}`;
    if (known.has(key)) return false;
    known.add(key);
    return true;
  });
}

function cleanAnswer(answer) {
  // The interface uses plain text. Normalize occasional model-emitted Markdown
  // bullets so compact replies retain the same minimal visual language.
  return String(answer || "").replace(/^\s*[*•]\s+/gm, "- ").trim();
}

function prioritizedHits(context, question) {
  const terms = [...new Set(String(question || "").toLowerCase().match(/[a-z0-9]{4,}/g) || [])];
  return [...(context.hits || [])].map((hit, index) => {
    const title = String(hit.title || "").toLowerCase();
    const text = String(hit.text || "").toLowerCase();
    const collection = String(hit.collection_id || "").toLowerCase();
    const relevance = terms.reduce((score, term) => score +
      (title.includes(term) ? 12 : 0) + (text.includes(term) ? 2 : 0), 0);
    const rcaScope = /(regional cabled array|cabled array|coszo|axial|hydrate ridge|oregon shelf|oregon offshore)/.test(`${title}\n${text}`) ? 10 : 0;
    const primaryCorpus = /^(instruments|websites|arcada|coszo)/.test(collection) ? 4 : 0;
    return { hit, index, score: relevance + rcaScope + primaryCorpus };
  }).sort((a, b) => b.score - a.score || a.index - b.index).slice(0, 6).map(({ hit }) => hit);
}

function answerMode(question) {
  const q = String(question || "").toLowerCase();
  // These questions need an inventory or a route to data, not a narrative
  // research synthesis. Keep the classifier deliberately narrow so broad
  // scientific questions retain the full evidence-first answer style.
  if (
    /\b(what|which)\b[^?]{0,80}\b(data|datasets?|files?)\b[^?]{0,80}\b(available|exist|download)/.test(q) ||
    /\b(where|how)\b[^?]{0,80}\b(download|get|access)\b/.test(q) ||
    /\b(list|show)\b[^?]{0,80}\b(data|datasets?|files?|sources?)\b/.test(q)
  ) return "compact";
  return "research";
}

function namedDataProduct(question) {
  const q = String(question || "").toLowerCase();
  for (const product of ["multidas", "optodas", "das25", "das24", "rapid"]) {
    if (q.includes(product)) return product;
  }
  return null;
}

function isDownloadQuestion(question) {
  return /\b(download|get|access)\b/.test(String(question || "").toLowerCase());
}

function directDownloadSource(question, hits) {
  const product = namedDataProduct(question);
  const route = {
    multidas: "/das25/data/multidas/",
    optodas: "/das25/data/optodas/",
    das24: "/das24/data/",
  }[product];
  if (!route) return null;
  return citations(hits).find((source) => source.url.toLowerCase().includes(route)) || null;
}

function selectedEvidenceHits(context, question) {
  const product = namedDataProduct(question);
  let hits = prioritizedHits(context, question);
  if (product) {
    const productHits = hits.filter((hit) =>
      `${hit.title || ""}\n${hit.text || ""}`.toLowerCase().includes(product),
    );
    if (productHits.length) hits = productHits;
  }
  return hits;
}

function evidencePackage(hits, sourceNumbers) {
  const sections = [];
  let remaining = MAX_EVIDENCE_CHARS;
  for (const hit of hits) {
    if (remaining <= 0) break;
    const refs = (hit.citations || []).map((c) => sourceNumbers.get(c.source_id || hit.chunk_id)).filter(Boolean);
    const header = `${hit.title}${refs.length ? ` | sources: ${refs.map((n) => `[${n}]`).join(" ")}` : ""}\n`;
    const text = String(hit.text || "").slice(0, Math.max(0, remaining - header.length));
    sections.push(`${header}${text}`);
    remaining -= header.length + text.length + 2;
  }
  return sections.join("\n\n");
}

async function postJson(url, body, headers = {}) {
  const result = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
    // The first local embedding request can warm the API model cache, and the
    // full evidence-to-answer path may cross a Cloudflare Tunnel. Keep a hard
    // ceiling, but allow that one bounded end-to-end request to complete.
    signal: AbortSignal.timeout(55_000),
  });
  if (!result.ok) throw new Error(`upstream ${result.status}`);
  return result.json();
}

async function generateAnswer(question, context, env) {
  const product = namedDataProduct(question);
  const evidenceHits = selectedEvidenceHits(context, question);
  const sourceList = citations(evidenceHits);
  const sourceNumbers = new Map(sourceList.map((source, index) => [source.id, index + 1]));
  const evidence = evidencePackage(evidenceHits, sourceNumbers);
  if (!evidence) throw new Error("no retrieved evidence");
  if (product && isDownloadQuestion(question) && sourceList[0]?.url) {
    return {
      answer: `You can download the requested ${product} data through the direct source link below.`,
      model: "RCA Atlas evidence routing",
    };
  }
  const sourceListText = sourceList.map((c) => c.title).join("; ");
  const mode = answerMode(question);
  const namedProductInstruction = product
    ? `The user specifically named ${product}; answer only about that named product. Do not include related products, file formats, instruments, or data types unless the evidence explicitly assigns them to ${product}.`
    : "";
  const compactInstruction = mode === "compact"
    ? `This is a data-availability, download, or list question. ${namedProductInstruction} Return a direct answer followed by at most four single-sentence bullets; each bullet names one available dataset or route, with its year or coverage and file type only when established. Use no sub-bullets, section headings, capability descriptions, deployment background, calibration details, or related literature. Keep the whole answer under 120 words. The interface renders links separately.`
    : "Write a complete, useful research answer from the evidence, but do not pad it with loosely related instruments, background, or speculation. For an instrument inventory question, identify every matching named instrument record you can support, then describe its identity, site or location, capabilities or measurements, and where its data are available when the evidence provides that.";
  const formatInstruction = mode === "compact"
    ? "Use plain text, with no Markdown hashes or asterisks. Obey the 120-word, single-sentence-bullet limit exactly."
    : "Structure the response as plain text: a brief direct answer, then section labels on their own lines and hyphen bullets where there are multiple locations, instruments, or findings. Do not use Markdown hashes or asterisks.";
  const prompt = `Retrieved RCA Atlas evidence:\n\n${evidence}\n\n---\nQuestion: ${question}\n\nRCA Atlas defaults to the OOI Regional Cabled Array and COSZO. Unless the user explicitly asks for a global comparison, answer in that scope and exclude tangential sites or literature outside it. First compare the individual named records in the evidence against the question. Then answer the user's exact question directly. Do not lead with a generic instrument definition when the user asks which instruments exist or where they are. ${compactInstruction} ${formatInstruction} State clearly what the evidence does not establish. Do not include citations, bracketed numbers, chunk IDs, source IDs, database identifiers, URLs, or any other provenance notation in the answer text. The interface renders the curated source list separately below the answer. Do not invent live values or tool results. Evidence sources available to you: ${sourceListText}`;
  const model = env.ANSWER_MODEL || "gemini-2.5-flash";
  const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(env.GEMINI_API_KEY)}`;
  const request = {
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    generationConfig: {
      temperature: 0.15,
      maxOutputTokens: mode === "compact" ? 400 : 4096,
      thinkingConfig: { thinkingBudget: mode === "compact" ? 128 : 1024 },
    },
  };

  // A temporary upstream 429/5xx must not discard an already-complete evidence
  // package. Retry once inside the Worker before returning an availability error.
  let lastError;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const upstream = await postJson(endpoint, request);
      const answer = upstream.candidates?.[0]?.content?.parts?.map((part) => part.text || "").join("").trim();
      if (!answer) throw new Error("model returned no answer");
      return { answer: cleanAnswer(answer), model };
    } catch (error) {
      lastError = error;
      if (attempt === 0) await new Promise((resolve) => setTimeout(resolve, 750));
    }
  }
  throw lastError;
}

function axialCountDay(question) {
  const q = question.toLowerCase();
  if (!/axial/.test(q) || !/(how many|count|number of)/.test(q) || !/earthquake/.test(q)) return null;
  const explicit = q.match(/\b(20\d{2}-\d{2}-\d{2})\b/);
  if (explicit) return explicit[1];
  const now = new Date();
  if (q.includes("yesterday")) now.setUTCDate(now.getUTCDate() - 1);
  else if (!q.includes("today")) return null;
  return now.toISOString().slice(0, 10);
}

async function liveAxialCount(question) {
  const day = axialCountDay(question);
  if (!day) return null;
  const stamp = day.replaceAll("-", "");
  const sourceUrl = `${AXIAL_CATALOG}/hypo71/hypo71_${stamp}.dat`;
  const upstream = await fetch(sourceUrl, { signal: AbortSignal.timeout(20_000) });
  if (!upstream.ok) throw new Error(`Axial catalog ${upstream.status}`);
  const catalog = await upstream.text();
  const count = catalog.split(/\r?\n/).filter((line) => {
    const parts = line.trim().split(/\s+/);
    return parts.length >= 18 && parts[0] === stamp;
  }).length;
  return {
    query: question,
    answer: `There were ${count} Axial Seamount earthquakes in the live catalog for ${day} UTC.`,
    answer_model: "axial_count_events (live catalog)",
    answer_citations: [{ id: "axial-live-catalog", title: "Axial Seamount Earthquake Catalog", url: sourceUrl }],
    hits: [], neighbors: [],
    tool_hints: [{ name: "axial_count_events", description: "Executed against the live daily Axial catalog", score: 1, required_arguments: ["day"], input_schema: { day } }],
  };
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("origin") || "";
    const cors = corsHeaders(env, origin);
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method === "GET" && url.pathname === "/health") return response({ status: "ok" }, 200, cors);
    if (request.method !== "POST" || url.pathname !== "/v1/answer") return response({ error: "not found" }, 404, cors);
    if (!validOrigin(origin, env)) return response({ error: "origin not allowed" }, 403, cors);
    const body = await readJson(request);
    const query = typeof body?.query === "string" ? body.query.trim() : "";
    if (query.length < 2 || query.length > MAX_QUERY_LENGTH) return response({ error: "invalid query" }, 400, cors);
    try {
      const liveToolResult = await liveAxialCount(query);
      if (liveToolResult) return response(liveToolResult, 200, cors);
      if (!env.GEMINI_API_KEY || !env.ATLAS_API_KEY || !env.ATLAS_API_ORIGIN) {
        return response({ error: "service is not configured" }, 503, cors);
      }
      const context = await postJson(`${env.ATLAS_API_ORIGIN.replace(/\/$/, "")}/v1/context`, {
        query, limit: MAX_HITS, graph_hops: MAX_GRAPH_HOPS, neighbors_per_seed: 8, tool_limit: 3,
      }, { "x-api-key": env.ATLAS_API_KEY });
      const evidenceHits = selectedEvidenceHits(context, query);
      const downloadSource = isDownloadQuestion(query) && directDownloadSource(query, evidenceHits);
      if (downloadSource) {
        const product = namedDataProduct(query);
        return response({
          query,
          answer: `You can download the requested ${product} data through the direct link below.`,
          answer_model: "RCA Atlas graph route",
          answer_citations: [downloadSource],
          hits: evidenceHits.map(publicHit), neighbors: context.neighbors || [], tool_hints: context.tool_hints || [],
        }, 200, cors);
      }
      const generated = await generateAnswer(query, context, env);
      return response({
        query, answer: generated.answer, answer_model: generated.model,
        answer_citations: citations(evidenceHits),
        hits: (context.hits || []).map(publicHit),
        neighbors: context.neighbors || [],
        tool_hints: context.tool_hints || [],
      }, 200, cors);
    } catch (error) {
      console.error("atlas answer failed", error instanceof Error ? error.message : "unknown");
      return response({ error: "answer temporarily unavailable" }, 503, cors);
    }
  },
};
