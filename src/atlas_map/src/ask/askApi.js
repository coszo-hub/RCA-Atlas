import { ATLAS_WORKER } from "../api/gateway.js";

// Development goes through Vite's /api/ask proxy (it adds the Origin the Worker accepts); the published map,
// served from coszo.org, calls the Worker directly.
export const ASK_URL = import.meta.env.PROD ? `${ATLAS_WORKER}/v1/answer` : "/api/ask";

// The models the Worker accepts; anything else it answers with Auto (Gemini first, then Groq).
export const MODELS = [
  ["auto", "Auto"], ["gemini-2.5-flash", "Gemini 2.5 Flash"], ["gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite"],
  ["groq-gpt-oss-120b", "GPT-OSS 120B"], ["groq-gpt-oss-20b", "GPT-OSS 20B"], ["groq-qwen3-8-27b", "Qwen3 27B"], ["gpt-5.4-mini", "GPT-5.4 mini"],
];

const LABELS = { "axial_count_events (live catalog)": "live catalog", "RCA Atlas graph route": "graph route",
  "RCA Atlas graph evidence (no LLM)": "no LLM", "RCA Atlas evidence routing": "evidence route" };
export const modelLabel = model => LABELS[model] ?? model ?? "";

// tz: the asker's IANA zone, so "today" and "yesterday" in a catalog question are their days, not UTC's.
const localZone = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined; } catch { return undefined; } };
export async function askAtlas(question, { model = "auto", tz = localZone(), signal, fetchImpl = fetch, now = () => performance.now() } = {}) {
  const t0 = now();
  let res;
  try {
    res = await fetchImpl(ASK_URL, { method: "POST", signal, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: question, answer_mode: "evidence", model, tz }) });
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    return { ok: false, message: "The Atlas answer service could not be reached." };
  }
  let data;
  try { data = await res.json(); } catch { return { ok: false, message: `The Atlas answer service did not respond (HTTP ${res.status}).` }; }
  if (!res.ok) {
    const why = typeof data?.error === "string" ? data.error : data?.error?.message;
    return { ok: false, message: why ? `${why[0].toUpperCase()}${why.slice(1).replace(/[.\s]+$/, "")} (HTTP ${res.status}).` : `The Atlas answer service failed (HTTP ${res.status}).` };
  }
  if (!data?.answer) return { ok: false, message: "The Atlas returned no answer." };
  return { ok: true, data, ms: now() - t0 };
}
