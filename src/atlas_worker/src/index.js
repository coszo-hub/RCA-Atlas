// Private Graph-RAG evidence -> Gemini synthesis boundary for RCA Atlas.
// Browser requests contain only a question. The Worker fetches evidence itself
// and returns stable corpus citations, never a Gemini key or Graph-RAG API key.

import { answerPrompt, axialDayWindow, evidencePackage, eventsInWindow, publicHit, sourceKey } from "./helpers.js";

const MAX_QUERY_LENGTH = 1_000;
const MAX_HITS = 10;
const MAX_GRAPH_HOPS = 2;
const AXIAL_CATALOG = "http://axial.ocean.washington.edu";

function corsHeaders(env, origin) {
  const allowed = env.ALLOWED_ORIGIN || "https://coszo.org";
  const allow = origin === allowed ? origin : allowed;
  return {
    "access-control-allow-origin": allow,
    "access-control-allow-methods": "GET, POST, OPTIONS",
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

const LIVE_GATEWAY_PATH = /^\/(?:status\/[A-Z0-9-]+|series\/[A-Z0-9-]+(?:\/variables)?|plots\/[A-Z0-9-]+|waveform\/[A-Z0-9.]+(?:\/health)?|files\/[A-Za-z0-9_-]+)$/;

async function proxyLiveData(env, url, cors) {
  if (!env.ATLAS_MAP_GATEWAY_ORIGIN) return response({ error: "live data service is not configured" }, 503, cors);
  const upstreamPath = url.pathname.replace(/^\/v1\/live/, "");
  // The gateway itself validates identifiers, but retain a narrow Worker
  // allowlist so it can never become a general proxy into the private VM.
  if (!LIVE_GATEWAY_PATH.test(upstreamPath)) return response({ error: "not found" }, 404, cors);
  try {
    const upstream = await fetch(`${env.ATLAS_MAP_GATEWAY_ORIGIN.replace(/\/$/, "")}${upstreamPath}${url.search}`, {
      headers: { accept: "application/json" }, signal: AbortSignal.timeout(30_000),
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        ...cors,
        "content-type": upstream.headers.get("content-type") || "application/json",
        "cache-control": upstream.headers.get("cache-control") || "no-store",
      },
    });
  } catch {
    return response({ error: { source: "Atlas live data", message: "live data service is temporarily unavailable" } }, 503, cors);
  }
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

function isInstrumentInventoryQuestion(question) {
  const q = String(question || "").toLowerCase();
  return /\b(sensor|sensors|instrument|instruments|equipment)\b/.test(q) &&
    /\b(site|location|located|deployed|seafloor|southern hydrate ridge|hydrate ridge)\b/.test(q);
}

function prioritizedHits(context, question, limit = 6) {
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
  }).sort((a, b) => b.score - a.score || a.index - b.index).slice(0, limit).map(({ hit }) => hit);
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

function isMultiSpanQuestion(question) {
  return /\bmulti[\s-]?span\b/.test(String(question || "").toLowerCase());
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

function namedDatasetDownloadAnswer(product) {
  const details = {
    multidas: {
      label: "DAS25 MultiDAS",
      format: "proprietary raw binary files",
      coverage: "the RCA north and south backbone cables",
      layout: "year/month/day/cable directories",
    },
    optodas: {
      label: "DAS25 OptoDAS",
      format: "HDF5 files",
      coverage: "the south cable's first span",
      layout: "year/month/day/cable directories",
    },
  }[product];
  if (!details) return `You can download the requested ${product} data through the direct link below.`;
  return `You can download the requested ${details.label} data through the direct link below.\n- Format: ${details.format}.\n- Coverage: ${details.coverage}.\n- Layout: ${details.layout}.`;
}

function multiSpanDownloadAnswer() {
  return "Multi-span DAS data for the 2025–2026 experiment can be downloaded from DAS25 MultiDAS.\n- Nokia multi-span DAS data are available as binary files.\n- OptoDAS data for the south cable are available as HDF5 files.\n- Data are organized by year, month, day, and cable.\n- Further reading and availability details are available through the linked documentation.";
}

function answerLinks(question, hits) {
  if (!isDownloadQuestion(question)) return [];
  const direct = directDownloadSource(question, hits);
  if (direct) return [direct];
  if (/\bmulti[\s-]?span\b/.test(String(question || "").toLowerCase())) {
    const multiDas = citations(hits).find((source) => /\/das25\/data\/multidas\/?$/i.test(source.url));
    if (multiDas) return [multiDas];
  }
  return citations(hits).filter((source) => source.url).slice(0, 2);
}

function selectedEvidenceHits(context, question) {
  const product = namedDataProduct(question);
  let hits = prioritizedHits(context, question, isInstrumentInventoryQuestion(question) ? 16 : 6);
  if (product) {
    const productHits = hits.filter((hit) =>
      `${hit.title || ""}\n${hit.text || ""}`.toLowerCase().includes(product),
    );
    if (productHits.length) hits = productHits;
  }
  return hits;
}

function quickGraphAnswer(context, question) {
  const genericTerms = new Set(["what", "which", "where", "when", "purpose", "instrument", "instruments", "available", "about", "there"]);
  const terms = [...new Set(String(question || "").toLowerCase().match(/[a-z0-9]{4,}/g) || [])]
    .filter((term) => !genericTerms.has(term));
  const hits = [...selectedEvidenceHits(context, question)].sort((a, b) => {
    const titleScore = (hit) => terms.reduce((score, term) => score +
      (String(hit.title || "").toLowerCase().includes(term) ? 100 : 0), 0);
    return titleScore(b) - titleScore(a);
  }).slice(0, 3);
  if (!hits.length) throw new Error("no retrieved evidence");
  const excerpt = (text) => {
    const normalized = String(text || "").replace(/\s+/g, " ").trim();
    const sentenceEnd = normalized.slice(0, 420).search(/[.!?](?:\s|$)/);
    return (sentenceEnd >= 0 ? normalized.slice(0, sentenceEnd + 1) : normalized.slice(0, 420)).trim();
  };
  const statements = hits.map((hit) => `- ${hit.title}: ${excerpt(hit.text)}`).filter((line) => !line.endsWith(": "));
  const entities = [...new Set((context.neighbors || []).slice(0, 6)
    .map((node) => node.name || node.local_id).filter(Boolean))];
  return [
    "Quick answer from RCA Atlas evidence (no language model):",
    ...statements,
    ...(entities.length ? [`Related graph entities: ${entities.join(", ")}.`] : []),
  ].join("\n");
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

const OPENAI_MODELS = new Set([
  "gpt-5.6-sol",
  "gpt-5.5",
  "gpt-5.5-pro",
  "gpt-5.4-mini",
]);
const GROQ_MODELS = {
  "groq-gpt-oss-120b": { id: "openai/gpt-oss-120b", label: "Groq GPT-OSS 120B" },
  "groq-gpt-oss-20b": { id: "openai/gpt-oss-20b", label: "Groq GPT-OSS 20B" },
  "groq-qwen3-8-27b": { id: "qwen/qwen3.8-27b", label: "Groq Qwen 3.8 27B" },
};
const OPENROUTER_FREE_MODELS = {
  "openrouter-glm-5-2": "z-ai/glm-5.2:free",
  "openrouter-qwen3-8-27b": "qwen/qwen3.8-27b:free",
  "openrouter-nex-n2-5-pro": "nex-agi/nex-n2.5-pro:free",
  "openrouter-gemma-4-31b": "google/gemma-4-31b-it:free",
};

async function generateGroqAnswer(prompt, mode, env, selected = GROQ_MODELS["groq-gpt-oss-120b"]) {
  if (!env.GROQ_API_KEY) throw new Error("Groq is not configured");
  const upstream = await postJson("https://api.groq.com/openai/v1/chat/completions", {
    model: selected.id,
    messages: [{ role: "user", content: prompt }],
    temperature: 0.15,
    max_tokens: mode === "compact" ? 400 : 4096,
  }, { authorization: `Bearer ${env.GROQ_API_KEY}` });
  const answer = upstream.choices?.[0]?.message?.content?.trim();
  if (!answer) throw new Error("Groq model returned no answer");
  return { answer: cleanAnswer(answer), model: selected.label };
}

async function generateOpenRouterAnswer(prompt, mode, env, selectedModel = env.OPENROUTER_FREE_MODEL || "z-ai/glm-5.2:free") {
  if (!env.OPENROUTER_API_KEY) throw new Error("OpenRouter is not configured");
  const upstream = await postJson("https://openrouter.ai/api/v1/chat/completions", {
    model: selectedModel,
    messages: [{ role: "user", content: prompt }],
    temperature: 0.15,
    max_tokens: mode === "compact" ? 400 : 4096,
  }, { authorization: `Bearer ${env.OPENROUTER_API_KEY}` });
  const answer = upstream.choices?.[0]?.message?.content?.trim();
  if (!answer) throw new Error("OpenRouter model returned no answer");
  return { answer: cleanAnswer(answer), model: `OpenRouter ${upstream.model || selectedModel}` };
}

async function generateOpenAIAnswer(prompt, requestedModel, mode, env) {
  if (!env.OPENAI_API_KEY) throw new Error("OpenAI is not configured");
  const upstream = await postJson("https://api.openai.com/v1/responses", {
    model: requestedModel,
    input: prompt,
    // Reasoning tokens count against max_output_tokens: a compact answer at medium effort spent all 400 on
    // reasoning and returned no text, so compact answers reason lightly within a larger budget (the prompt
    // still holds the answer to 120 words).
    reasoning: { effort: requestedModel === "gpt-5.6-sol" ? "high" : mode === "compact" ? "low" : "medium" },
    max_output_tokens: mode === "compact" ? 1200 : 4096,
    store: false,
  }, { authorization: `Bearer ${env.OPENAI_API_KEY}` });
  const answer = upstream.output_text || upstream.output?.flatMap((item) => item.content || [])
    .map((item) => item.text || "").join("").trim();
  if (!answer) throw new Error("OpenAI model returned no answer");
  return { answer: cleanAnswer(answer), model: `OpenAI ${requestedModel}` };
}

async function generateAnswer(question, context, env, requestedModel = "auto") {
  const product = namedDataProduct(question);
  const evidenceHits = selectedEvidenceHits(context, question);
  const sourceList = citations(evidenceHits);
  // Sources sharing an id (one PI portal record, several routes) are told apart by URL, as citations() dedupes them.
  const sourceNumbers = new Map(sourceList.map((source, index) => [sourceKey(source.id, source.url), index + 1]));
  const evidence = evidencePackage(evidenceHits, sourceNumbers);
  if (!evidence) throw new Error("no retrieved evidence");
  if (product && isDownloadQuestion(question) && sourceList[0]?.url) {
    return {
      answer: `You can download the requested ${product} data through the direct source link below.`,
      model: "RCA Atlas evidence routing",
    };
  }
  const mode = answerMode(question);
  const prompt = answerPrompt({ question, evidence, sources: sourceList, mode, product });
  if (GROQ_MODELS[requestedModel]) return generateGroqAnswer(prompt, mode, env, GROQ_MODELS[requestedModel]);
  if (OPENAI_MODELS.has(requestedModel)) return generateOpenAIAnswer(prompt, requestedModel, mode, env);
  const model = ["gemini-2.5-flash", "gemini-3.5-flash-lite"].includes(requestedModel)
    ? requestedModel : (env.ANSWER_MODEL || "gemini-2.5-flash");
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
  // Auto stays Gemini-first for its native evidence handling. Each free route
  // is attempted independently: a temporary quota or capacity failure moves to
  // the next provider rather than ending the answer request.
  if (requestedModel === "auto" && env.GROQ_API_KEY) {
    try {
      return await generateGroqAnswer(prompt, mode, env);
    } catch (error) {
      lastError = error;
    }
  }
  // Last, a paid route when one is configured, so Auto still answers when every free route is out of quota.
  if (requestedModel === "auto" && env.OPENAI_API_KEY) {
    try {
      return await generateOpenAIAnswer(prompt, "gpt-5.4-mini", mode, env);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

async function liveAxialCount(question, tz) {
  const window = axialDayWindow(question, { tz });
  if (!window) return null;
  const urls = window.stamps.map((stamp) => `${AXIAL_CATALOG}/hypo71/hypo71_${stamp}.dat`);
  // A local day can reach into a UTC day the catalog has not started yet; only a day with no file at all fails.
  const files = (await Promise.all(urls.map(async (url, i) => {
    const upstream = await fetch(url, { signal: AbortSignal.timeout(20_000) });
    if (upstream.status === 404 && i > 0) return null;
    if (!upstream.ok) throw new Error(`Axial catalog ${upstream.status}`);
    return [await upstream.text(), window.stamps[i], url];
  }))).filter(Boolean);
  const events = eventsInWindow(files, window), n = events.length;
  const utc = window.tz === "UTC";
  const answer = utc
    ? `There ${window.today ? "have been" : "were"} ${n} Axial Seamount earthquakes in the live catalog for ${window.day} UTC${window.today ? " so far" : ""}.`
    : window.today
      ? `There have been ${n} Axial Seamount earthquakes so far today, ${window.label} (${window.zoneName}), in the live catalog.`
      : `There were ${n} Axial Seamount earthquakes on ${window.label} (${window.zoneName}) in the live catalog.`;
  return {
    query: question,
    answer,
    answer_model: "axial_count_events (live catalog)",
    answer_citations: files.map(([, stamp, url]) => ({ id: files.length > 1 ? `axial-live-catalog-${stamp}` : "axial-live-catalog",
      title: files.length > 1 ? `Axial Seamount Earthquake Catalog, ${stamp.slice(0, 4)}-${stamp.slice(4, 6)}-${stamp.slice(6)} UTC` : "Axial Seamount Earthquake Catalog", url })),
    hits: [], neighbors: [], events,
    tool_hints: [{ name: "axial_count_events", description: "Executed against the live daily Axial catalog", score: 1, required_arguments: ["day"],
      input_schema: { day: window.day, tz: window.tz, label: window.label, today: window.today } }],
  };
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("origin") || "";
    const cors = corsHeaders(env, origin);
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method === "GET" && url.pathname === "/health") return response({ status: "ok" }, 200, cors);
    if (request.method === "GET" && url.pathname.startsWith("/v1/live/")) return proxyLiveData(env, url, cors);
    if (request.method !== "POST" || url.pathname !== "/v1/answer") return response({ error: "not found" }, 404, cors);
    if (!validOrigin(origin, env)) return response({ error: "origin not allowed" }, 403, cors);
    const body = await readJson(request);
    const query = typeof body?.query === "string" ? body.query.trim() : "";
    const quick = body?.answer_mode === "quick";
    const requestedModel = ["gemini-2.5-flash", "gemini-3.5-flash-lite", ...Object.keys(GROQ_MODELS), ...OPENAI_MODELS].includes(body?.model)
      ? body.model : "auto";
    if (query.length < 2 || query.length > MAX_QUERY_LENGTH) return response({ error: "invalid query" }, 400, cors);
    try {
      const liveToolResult = await liveAxialCount(query, typeof body?.tz === "string" ? body.tz.slice(0, 64) : undefined);
      if (liveToolResult) return response(liveToolResult, 200, cors);
      if (!env.ATLAS_API_KEY || !env.ATLAS_API_ORIGIN) {
        return response({ error: "service is not configured" }, 503, cors);
      }
      const context = await postJson(`${env.ATLAS_API_ORIGIN.replace(/\/$/, "")}/v1/context`, {
        query, limit: isInstrumentInventoryQuestion(query) ? 24 : MAX_HITS,
        graph_hops: MAX_GRAPH_HOPS, neighbors_per_seed: isInstrumentInventoryQuestion(query) ? 16 : 8, tool_limit: 3,
      }, { "x-api-key": env.ATLAS_API_KEY });
      const evidenceHits = selectedEvidenceHits(context, query);
      const downloadSource = isDownloadQuestion(query) && directDownloadSource(query, evidenceHits);
      const multiSpanSource = isDownloadQuestion(query) && isMultiSpanQuestion(query)
        ? citations(evidenceHits).find((source) => /\/das25\/data\/multidas\/?$/i.test(source.url))
        : null;
      if (multiSpanSource) {
        return response({
          query, answer: multiSpanDownloadAnswer(), answer_model: "RCA Atlas graph route",
          answer_citations: [multiSpanSource], answer_links: [multiSpanSource],
          hits: evidenceHits.map(publicHit), neighbors: context.neighbors || [], tool_hints: context.tool_hints || [],
        }, 200, cors);
      }
      if (downloadSource) {
        const product = namedDataProduct(query);
        return response({
          query,
          answer: namedDatasetDownloadAnswer(product),
          answer_model: "RCA Atlas graph route",
          answer_citations: [downloadSource], answer_links: [downloadSource],
          hits: evidenceHits.map(publicHit), neighbors: context.neighbors || [], tool_hints: context.tool_hints || [],
        }, 200, cors);
      }
      if (quick) {
        return response({
          query,
          answer: quickGraphAnswer(context, query),
          answer_model: "RCA Atlas graph evidence (no LLM)",
          answer_citations: citations(evidenceHits),
          answer_links: answerLinks(query, evidenceHits),
          hits: (context.hits || []).map(publicHit),
          neighbors: context.neighbors || [],
          tool_hints: context.tool_hints || [],
        }, 200, cors);
      }
      const generated = await generateAnswer(query, context, env, requestedModel);
      return response({
        query, answer: generated.answer, answer_model: generated.model,
        answer_citations: citations(evidenceHits),
        answer_links: answerLinks(query, evidenceHits),
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
