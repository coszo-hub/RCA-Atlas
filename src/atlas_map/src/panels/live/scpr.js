// The cabled SCPR's hourly CSV (Axial-Seamount/self-calibrating-pressure), regenerated daily and read straight from
// GitHub. Lines starting with # describe the file; then a header row and one row per hour, empty where a value is
// missing (a calibration, a drift too uncertain to remove, or uplift within ~1.5 days of a gap).

export const GAUGES = [
  { label: "PARO1", stroke: "#ecebe6" },
  { label: "PARO2", stroke: "#c98500" },   // the pressure family's colour
];
export const MEASURES = [
  { key: "uplift", label: "Seafloor uplift", unit: "m", cols: ["paro1_uplift_m", "paro2_uplift_m"], scale: 1 },
  { key: "corr", label: "Drift-corrected pressure", unit: "kPa", cols: ["paro1_corr_pa", "paro2_corr_pa"], scale: 1e-3 },
  { key: "raw", label: "Raw pressure", unit: "kPa", cols: ["paro1_raw_pa", "paro2_raw_pa"], scale: 1e-3 },
];
export const RANGES = { "30d": 30 * 86400e3, "1y": 365 * 86400e3, All: Infinity };

export function parseScpr(text) {
  const lines = text.split(/\r?\n/);
  const notes = lines.filter(l => l.startsWith("#")).join("\n");
  const rows = lines.filter(l => l && !l.startsWith("#"));
  if (!rows.length) return { error: "the file has no rows" };
  const header = rows[0].split(",");
  const wanted = MEASURES.flatMap(m => m.cols);
  const missing = ["time_utc", ...wanted].filter(c => !header.includes(c));
  if (missing.length) return { error: `the file has no ${missing.join(", ")} column${missing.length > 1 ? "s" : ""}` };
  const ti = header.indexOf("time_utc"), idx = wanted.map(c => header.indexOf(c));
  const t = [], cols = Object.fromEntries(wanted.map(c => [c, []]));
  for (const row of rows.slice(1)) {
    const f = row.split(",");
    const ms = Date.parse(f[ti]);
    if (Number.isNaN(ms)) continue;
    t.push(ms);
    wanted.forEach((c, j) => { const v = f[idx[j]]; cols[c].push(v === "" || v == null ? null : Number(v)); });
  }
  if (!t.length) return { error: "the file has no readable rows" };
  return {
    t, cols,
    generated: notes.match(/generated (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z?)/)?.[1] ?? null,
    provisionalAfter: notes.match(/after the last calibration\s*#?\s*\((\d{4}-\d{2}-\d{2})\)/)?.[1] ?? null,
  };
}

const HOUR = 3600e3;

// The file's own tidal filter (scpr_export.py's godin): running means of 24, 24 and 25 hours, each null where its
// window is less than 90 % covered, so about a day next to a gap or either end of the file is left out. The file
// omits missing hours as rows, so the values go back on an hourly grid first; windows align as numpy's "same".
export function godin(t, values) {
  const n = Math.round((t[t.length - 1] - t[0]) / HOUR) + 1;
  let y = new Float64Array(n).fill(NaN);
  t.forEach((ms, i) => { if (values[i] != null) y[Math.round((ms - t[0]) / HOUR)] = values[i]; });
  for (const w of [24, 24, 25]) {
    const sum = new Float64Array(n + 1), cnt = new Float64Array(n + 1);
    for (let i = 0; i < n; i++) {
      const ok = !Number.isNaN(y[i]);
      sum[i + 1] = sum[i] + (ok ? y[i] : 0);
      cnt[i + 1] = cnt[i] + (ok ? 1 : 0);
    }
    const ahead = (w - 1) >> 1, out = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const lo = Math.max(0, i + ahead - w + 1), hi = Math.min(n, i + ahead + 1);
      const k = cnt[hi] - cnt[lo];
      out[i] = k >= 0.9 * w ? (sum[hi] - sum[lo]) / k : NaN;
    }
    y = out;
  }
  return t.map(ms => { const v = y[Math.round((ms - t[0]) / HOUR)]; return Number.isNaN(v) ? null : v; });
}

const detidedCache = new WeakMap();
function detided(data, col) {
  if (!detidedCache.has(data)) detidedCache.set(data, {});
  const c = detidedCache.get(data);
  return (c[col] ??= godin(data.t, data.cols[col]));
}

// The chart's lines for one measurement over the range ending at the newest row, in the measurement's unit;
// with `detide`, a pressure's tides are removed as the file removes them for uplift (uplift is already detided).
export function scprLines(data, measureKey, range, detide = false) {
  const m = MEASURES.find(x => x.key === measureKey) ?? MEASURES[0];
  const tidesOut = detide && m.key !== "uplift";
  const col = c => (tidesOut ? detided(data, c) : data.cols[c]);
  const start = data.t[data.t.length - 1] - (RANGES[range] ?? Infinity);
  let i0 = 0;
  while (i0 < data.t.length && data.t[i0] < start) i0++;
  const series = m.cols.map((c, j) => ({ ...GAUGES[j], values: col(c).slice(i0).map(v => (v == null ? null : v * m.scale)) }));
  const count = data.t.length - i0;
  // The corrected and uplift columns can stop well before the raw one (the file blanks them once the drift is too
  // uncertain), so each measurement reports its own newest value, wherever the range is.
  let last = data.t.length - 1;
  while (last >= 0 && m.cols.every(c => col(c)[last] == null)) last--;
  return { x: data.t.slice(i0), series, measure: m, count, readings: series.some(s => s.values.some(v => v != null)),
    lastValueAt: last >= 0 ? data.t[last] : null };
}

export async function fetchScpr(url, { signal, fetchImpl = fetch } = {}) {
  let r;
  try {
    r = await fetchImpl(url, { signal });
  } catch (e) {
    if (e?.name === "AbortError") throw e;
    return { ok: false, kind: "upstream", source: "GitHub", message: "the SCPR file could not be reached" };
  }
  if (!r.ok) return { ok: false, kind: "upstream", source: "GitHub", message: `the SCPR file returned HTTP ${r.status}` };
  const parsed = parseScpr(await r.text());
  return parsed.error ? { ok: false, kind: "bad", source: "SCPR file", message: parsed.error } : { ok: true, data: parsed };
}
