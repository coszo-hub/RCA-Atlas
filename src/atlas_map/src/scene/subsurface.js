import { toX, toZ } from "./geo.js";

// Earthquake rows are [dLon / scale, dLat / scale, metres below sea level, days since day0], sorted by time. The
// relocated catalog gives no magnitude (-99, as shaders cannot test for NaN).
export function quakeArrays(eq) {
  const n = eq.rows.length, positions = new Float32Array(n * 3), elev = new Float32Array(n), day = new Float32Array(n);
  eq.rows.forEach(([a, b, d, t], i) => {
    positions[i * 3] = toX(eq.lon0 + a * eq.scale); positions[i * 3 + 2] = toZ(eq.lat0 + b * eq.scale);
    elev[i] = -d; day[i] = t;
  });
  return { positions, elev, day, mag: new Float32Array(n).fill(-99) };
}

// The real-time catalog after the relocated one (axial_unrest.py): little-endian int32 rows of [dLon, dLat] / scale,
// metres below sea level, minutes since meta.day0 and Mw x 100, sorted by time. Days are counted from day0, the
// relocated catalog's first day, so both share one timeline.
export function realtimeArrays(meta, buffer, day0) {
  const a = new Int32Array(buffer), W = meta.fields.length, n = a.length / W;
  const shift = (Date.parse(`${meta.day0}T00:00:00Z`) - Date.parse(`${day0}T00:00:00Z`)) / 86400000;
  const positions = new Float32Array(n * 3), elev = new Float32Array(n), day = new Float32Array(n), mag = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const r = i * W;
    positions[i * 3] = toX(meta.lon0 + a[r] * meta.scale); positions[i * 3 + 2] = toZ(meta.lat0 + a[r + 1] * meta.scale);
    elev[i] = -a[r + 2]; day[i] = a[r + 3] / 1440 + shift; mag[i] = a[r + 4] / 100;
  }
  return { positions, elev, day, mag };
}

// Two sets of quake arrays, the second all later than the first, as one.
export function joinQuakes(a, b) {
  const cat = (x, y) => { const out = new Float32Array(x.length + y.length); out.set(x); out.set(y, x.length); return out; };
  return { positions: cat(a.positions, b.positions), elev: cat(a.elev, b.elev), day: cat(a.day, b.day), mag: cat(a.mag, b.mag) };
}

// The unrest strip beneath the month slider: month i's bar height (0..1, log scale: 1 to the busiest month) and the
// uplift line, one point a day, as [x 0..1 across the months, y 0..1 within the uplift's range], gaps as breaks.
export function unrestStrip(unrest, monthList, day0) {
  const counts = unrest.monthly.counts, top = Math.log10(Math.max(...counts) + 1);
  const offset = monthIndex(unrest.monthly.start) - monthIndex(monthList[0].label);
  const bars = monthList.map((_, i) => { const c = counts[i - offset] ?? 0; return { count: c, h: Math.log10(c + 1) / top }; });
  const span = monthList[monthList.length - 1].end, start = Date.parse(`${day0}T00:00:00Z`);
  const from = Date.parse(`${unrest.uplift.start}T00:00:00Z`);
  const lines = {}, all = Object.values(unrest.uplift.sites).flat().filter(v => v != null);
  const lo = Math.min(...all), hi = Math.max(...all);
  for (const [site, values] of Object.entries(unrest.uplift.sites)) {
    const segs = [[]];
    values.forEach((v, i) => {
      const d = (from - start) / 86400000 + i;
      if (v == null || d < 0 || d > span) { if (segs[segs.length - 1].length) segs.push([]); return; }
      segs[segs.length - 1].push([d / span, (v - lo) / (hi - lo)]);
    });
    lines[site] = segs.filter(s => s.length > 1);
  }
  const latest = Object.fromEntries(Object.entries(unrest.uplift.sites).map(([k, v]) => [k, v.filter(x => x != null).at(-1)]));
  return { bars, lines, zero: (0 - lo) / (hi - lo), lo, hi, latest };
}

// The uplift (cm) at a site on the last day of month i with a value, looking back at most 45 days (the Gold Copy's
// daily depths come a week or two late), or null.
export function upliftAt(unrest, site, monthList, i, day0) {
  const lead = (Date.parse(`${day0}T00:00:00Z`) - Date.parse(`${unrest.uplift.start}T00:00:00Z`)) / 86400000;
  const values = unrest.uplift.sites[site], last = Math.floor(lead + monthList[i].end - 1);
  for (let k = Math.min(last, values.length - 1); k >= 0 && k > last - 46; k--) if (values[k] != null) return values[k];
  return null;
}

function monthIndex(label) { const [y, m] = label.split("-").map(Number); return y * 12 + m - 1; }

// A rows×cols grid of [lon, lat, elevation m] or null; a cell becomes two triangles only when all its corners exist.
export function surfaceArrays({ rows, cols, points }) {
  const positions = new Float32Array(rows * cols * 3), elev = new Float32Array(rows * cols), index = [];
  points.forEach((p, i) => { if (p) { positions[i * 3] = toX(p[0]); positions[i * 3 + 2] = toZ(p[1]); elev[i] = p[2]; } });
  for (let r = 0; r < rows - 1; r++) for (let c = 0; c < cols - 1; c++) {
    const a = r * cols + c, b = a + 1, d = a + cols, e = d + 1;
    if (points[a] && points[b] && points[d] && points[e]) index.push(a, d, b, b, d, e);
  }
  return { positions, elev, index: new Uint32Array(index) };
}

// Calendar months (UTC) covering the catalog; each ends, in days since day0, where the next begins.
export function months(day0, lastDay) {
  const start = Date.parse(`${day0}T00:00:00Z`), d = new Date(start), out = [];
  for (let y = d.getUTCFullYear(), m = d.getUTCMonth(); ; m++) {
    const end = (Date.UTC(y, m + 1, 1) - start) / 86400000;
    out.push({ label: new Date(Date.UTC(y, m, 1)).toISOString().slice(0, 7), end });
    if (end > lastDay) return out;
  }
}

// How many of the sorted days fall before t.
export function countBefore(days, t) {
  let lo = 0, hi = days.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (days[mid] < t) lo = mid + 1; else hi = mid; }
  return lo;
}

// The terrain turns to glass inside this circle (world units) so the layers beneath show through.
// It covers every surface vertex and 98% of the earthquakes, plus a margin.
export function glassWindow(data, marginKm = 1.2) {
  let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
  const pts = [];
  for (const s of data.surfaces) for (const p of s.points) if (p) pts.push([toX(p[0]), toZ(p[1]), true]);
  const eq = data.earthquakes;
  for (const [a, b] of eq.rows) pts.push([toX(eq.lon0 + a * eq.scale), toZ(eq.lat0 + b * eq.scale), false]);
  for (const [x, z] of pts) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); z0 = Math.min(z0, z); z1 = Math.max(z1, z); }
  const x = (x0 + x1) / 2, z = (z0 + z1) / 2;
  const rs = pts.filter(p => !p[2]).map(([px, pz]) => Math.hypot(px - x, pz - z)).sort((a, b) => a - b);
  let r = rs.length ? rs[Math.floor(0.98 * (rs.length - 1))] : 0;
  for (const [px, pz, surf] of pts) if (surf) r = Math.max(r, Math.hypot(px - x, pz - z));
  return { x, z, r: r + marginKm };
}
