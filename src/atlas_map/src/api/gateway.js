import { GATEWAY } from "../data/paths.js";

const KIND = { 404: "notfound", 422: "bad", 502: "upstream", 503: "busy", 504: "timeout" };

export async function api(path, { signal, method = "GET", body, fetchImpl = fetch } = {}) {
  let res;
  try {
    res = await fetchImpl(`${GATEWAY}${path}`, { signal, method, headers: body ? { "Content-Type": "application/json" } : undefined,
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
export const chat = (question, o) => api("/chat", { ...o, method: "POST", body: { question } });
