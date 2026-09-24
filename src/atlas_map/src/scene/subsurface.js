import { toX, toZ } from "./geo.js";

// Earthquake rows are [dLon / scale, dLat / scale, metres below sea level, days since day0], sorted by time.
export function quakeArrays(eq) {
  const n = eq.rows.length, positions = new Float32Array(n * 3), elev = new Float32Array(n), day = new Float32Array(n);
  eq.rows.forEach(([a, b, d, t], i) => {
    positions[i * 3] = toX(eq.lon0 + a * eq.scale); positions[i * 3 + 2] = toZ(eq.lat0 + b * eq.scale);
    elev[i] = -d; day[i] = t;
  });
  return { positions, elev, day };
}

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
