import { KX, KZ } from "./geo.js";

// The pure parts of the evidence layer: spike sizes, the rise/sink timing, off-screen chips, card placement, grouping.

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const easeOut = t => 1 - Math.pow(1 - t, 3);

// World height (km) of a spike: a fixed share of the view, so it reads the same at region and close zoom.
export const spikeHeight = (dist, active = false) => clamp(dist * 0.085, 0.12, 70) * (active ? 1.8 : 1);

// Spikes rise one after another, `stagger` ms apart, `dur` ms each; they sink together.
export const riseAt = (ms, i, reduced = false, stagger = 120, dur = 600) => (reduced ? 1 : easeOut(clamp((ms - i * stagger) / dur, 0, 1)));
export const sinkAt = (ms, reduced = false, dur = 300) => (reduced ? 0 : 1 - easeOut(clamp(ms / dur, 0, 1)));

// Hypocentres appear in time order (order 0..1 through the day) over `dur` ms.
export const eventShown = (order, ms, reduced = false, dur = 3000) => reduced || ms >= order * dur;

// A quake's point size in pixels by magnitude (Axial's are mostly M -0.5 to 2).
export const quakePx = mag => 7 + 6 * clamp((mag ?? -1) + 1, 0, 4);

// A chip for evidence outside the free area (or behind the camera): on the free area's edge, `margin` px in, in the
// direction of the point from the area's centre. p is [x, y, z] from scene.project (z > 1 is behind the camera).
export function edgeChip([px, py, pz], rect, margin = 18) {
  const behind = pz > 1;
  if (!behind && px >= rect.left && px <= rect.right && py >= rect.top && py <= rect.bottom) return null;
  const cx = (rect.left + rect.right) / 2, cy = (rect.top + rect.bottom) / 2;
  let dx = px - cx, dy = py - cy;
  if (behind) { dx = -dx; dy = -dy; }
  if (!dx && !dy) dy = 1;
  const hw = (rect.right - rect.left) / 2 - margin, hh = (rect.bottom - rect.top) / 2 - margin;
  const k = Math.min(dx ? hw / Math.abs(dx) : Infinity, dy ? hh / Math.abs(dy) : Infinity);
  return { x: Math.round(cx + dx * k), y: Math.round(cy + dy * k), angle: Math.atan2(dy, dx) };
}

// The in-scene card: above the spike's top when it fits, else beside it (right, then left), inside the free area.
export function placeCard([tx, ty], [bx, by], { w, h }, rect, gap = 14, m = 8) {
  const fitX = x => clamp(x, rect.left + m, rect.right - w - m), fitY = y => clamp(y, rect.top + m, rect.bottom - h - m);
  if (ty - gap - h >= rect.top + m) return { x: fitX(tx - w / 2), y: fitY(ty - gap - h), side: "above" };
  const y = fitY(Math.min(ty, by - h));
  if (tx + gap + w <= rect.right - m) return { x: tx + gap, y, side: "right" };
  return { x: Math.max(rect.left + m, tx - gap - w), y, side: "left" };
}

// One spike per location: items sharing a position merge their numbers (the first item's colour leads).
// Cables have no spike; they glow along their route.
export function groupSpikes(located) {
  const spikes = [], byKey = new Map(), cables = [];
  for (const it of located) {
    if (it.kind === "cable") { cables.push(it); continue; }
    const key = `${it.lon.toFixed(4)},${it.lat.toFixed(4)}`;
    let s = byKey.get(key);
    if (!s) { s = { key, ns: [], items: [], lon: it.lon, lat: it.lat, color: it.color, kind: it.kind }; byKey.set(key, s); spikes.push(s); }
    s.ns.push(it.n); s.items.push(it);
  }
  return { spikes, cables };
}

// A view (for scene.fit / flyTo) that frames all the points: centred on their extent, distance from their spread.
export function frameView(points, { az, exag, polar = 0.8 }) {
  const lons = points.map(p => p[0]), lats = points.map(p => p[1]);
  const [lo0, lo1, la0, la1] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)];
  const spread = Math.hypot((lo1 - lo0) * KX, (la1 - la0) * KZ);
  return { ll: [(lo0 + lo1) / 2, (la0 + la1) / 2], dist: Math.max(9, spread * 2.4), polar, az, exag };
}
