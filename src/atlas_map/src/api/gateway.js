const KIND = { 404: "notfound", 422: "bad", 502: "upstream", 503: "busy", 504: "timeout" };
const ATLAS_WORKER = "https://rca-atlas.quakehunt.workers.dev";

export async function api(path, { signal, method = "GET", body, fetchImpl = fetch } = {}) {
  let res;
  try {
    res = await fetchImpl(`/api${path}`, { signal, method, headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined });
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    return { ok: false, kind: "unreachable", source: "gateway", message: "The live data service is not running." };
  }
  let data;
  try { data = await res.json(); } catch { data = null; }
  if (res.ok) return { ok: true, data };
  if (!data?.error) return { ok: false, kind: "unreachable", source: "gateway", message: "The live data service is not running." };
  return { ok: false, kind: KIND[res.status] ?? "upstream", source: data.error.source, message: data.error.message };
}

const q = params => new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== "")).toString();
export const status = (refdes, o) => api(`/status/${encodeURIComponent(refdes)}`, o);
export const variables = (refdes, o) => api(`/series/${encodeURIComponent(refdes)}/variables`, o);
export const series = (refdes, p, o) => api(`/series/${encodeURIComponent(refdes)}?${q(p)}`, o);
export const plots = (refdes, o) => api(`/plots/${encodeURIComponent(refdes)}`, o);
export const waveform = (station, minutes, channel, o) => api(`/waveform/${station}?${q({ minutes, channel })}`, o);
export const files = (key, endpoint, path, o) => api(`/files/${encodeURIComponent(key)}?${q({ endpoint, path })}`, o);
export async function chat(question, { signal, fetchImpl = fetch } = {}) {
  let response;
  try {
    response = await fetchImpl(`${ATLAS_WORKER}/v1/answer`, {
      method: "POST", signal, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: question, answer_mode: "evidence" }),
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    return { ok: false, kind: "unreachable", source: "RCA Atlas", message: "The Graph-RAG service is unavailable." };
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.answer) return { ok: false, kind: KIND[response.status] ?? "upstream", source: "RCA Atlas", message: data.error || "The Graph-RAG service is unavailable." };
  return { ok: true, data: { answer: data.answer, citations: data.answer_citations || [] } };
}
