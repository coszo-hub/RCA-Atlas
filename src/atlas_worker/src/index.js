// Private Graph-RAG evidence -> Gemini synthesis boundary for RCA Atlas.
// Browser requests contain only a question. The Worker fetches evidence itself
// and returns stable corpus citations, never a Gemini key or Graph-RAG API key.

const MAX_QUERY_LENGTH = 1_000;
const MAX_HITS = 10;
const MAX_GRAPH_HOPS = 2;
const MAX_EVIDENCE_CHARS = 18_000;

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
    title: citation.title || hit.title,
    url: citation.url || "",
  }))).filter((citation) => {
    const key = `${citation.id}|${citation.url}`;
    if (known.has(key)) return false;
    known.add(key);
    return true;
  });
}

function evidencePackage(context) {
  const sections = [];
  let remaining = MAX_EVIDENCE_CHARS;
  for (const hit of context.hits || []) {
    if (remaining <= 0) break;
    const citationIds = (hit.citations || []).map((c) => c.source_id).filter(Boolean).join(", ");
    const header = `[${hit.chunk_id}] ${hit.title}${citationIds ? ` | sources: ${citationIds}` : ""}\n`;
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
  const evidence = evidencePackage(context);
  if (!evidence) throw new Error("no retrieved evidence");
  const citationList = citations(context.hits || []).map((c) => `[${c.id}]`).join(", ");
  const prompt = `Retrieved RCA Atlas evidence:\n\n${evidence}\n\n---\nQuestion: ${question}\n\nAnswer only from the evidence. If it is insufficient, say so. Cite every factual claim using the stable source IDs shown in square brackets. Do not invent URLs, live values, or tool results. Available source IDs: ${citationList}`;
  const model = env.ANSWER_MODEL || "gemini-2.5-flash";
  const upstream = await postJson(
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(env.GEMINI_API_KEY)}`,
    {
      contents: [{ role: "user", parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0.15, maxOutputTokens: 700 },
    },
  );
  const answer = upstream.candidates?.[0]?.content?.parts?.map((part) => part.text || "").join("").trim();
  if (!answer) throw new Error("model returned no answer");
  return { answer, model };
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
    if (!env.GEMINI_API_KEY || !env.ATLAS_API_KEY || !env.ATLAS_API_ORIGIN) {
      return response({ error: "service is not configured" }, 503, cors);
    }
    const body = await readJson(request);
    const query = typeof body?.query === "string" ? body.query.trim() : "";
    if (query.length < 2 || query.length > MAX_QUERY_LENGTH) return response({ error: "invalid query" }, 400, cors);
    try {
      const context = await postJson(`${env.ATLAS_API_ORIGIN.replace(/\/$/, "")}/v1/context`, {
        query, limit: MAX_HITS, graph_hops: MAX_GRAPH_HOPS, neighbors_per_seed: 8, tool_limit: 3,
      }, { "x-api-key": env.ATLAS_API_KEY });
      const generated = await generateAnswer(query, context, env);
      return response({
        query, answer: generated.answer, answer_model: generated.model,
        answer_citations: citations(context.hits || []),
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
