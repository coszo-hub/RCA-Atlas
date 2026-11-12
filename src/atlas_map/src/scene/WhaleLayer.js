import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { toX, toZ } from "./geo.js";
import { atlasUrl } from "../data/bundle.js";

// One colour a track; calls in no track are grey.
export const TRACK_COLORS = ["#7fb2ff", "#ffcc85", "#9be59b", "#f28fb1", "#c6a3ff", "#62d7d2", "#ffe27a", "#ff9d6c"];
const UNTRACKED = "#9a988f";
const LIFT_M = 25;   // above the seafloor, so the dots are not buried in the relief

export async function loadWhales(fetchImpl = fetch) {
  try {
    const res = await fetchImpl(atlasUrl("whales.json"));
    if (!res.ok || res.headers?.get("content-type")?.includes("html")) return null;
    const data = await res.json();
    return Object.keys(data.days ?? {}).length ? data : null;
  } catch { return null; }
}

// A day's calls grouped into tracks, each in time order: { id: [[lon, lat, seconds], ...] }, and the untracked calls.
export function dayTracks(day) {
  const tracks = {}, loose = [];
  for (const [lon, lat, id, t] of day.calls) (id ? (tracks[id] ??= []) : loose).push([lon, lat, t]);
  for (const k of Object.keys(tracks)) tracks[k].sort((a, b) => a[2] - b[2]);
  return { tracks, loose };
}

// A track's path: the running mean of its calls' positions, k calls either side (fewer at the ends). The locator grids
// positions at 0.2 km, so joining the raw calls zigzags between neighbouring grid points.
export function smoothTrack(pts, k = 3) {
  return pts.map((_, i) => {
    const w = pts.slice(Math.max(0, i - k), i + k + 1);
    return [w.reduce((a, p) => a + p[0], 0) / w.length, w.reduce((a, p) => a + p[1], 0) / w.length];
  });
}

// The middle and size (world units) of a day's calls, for framing them.
export function dayExtent(day) {
  const xs = day.calls.map(c => toX(c[0])), zs = day.calls.map(c => toZ(c[1]));
  const x0 = Math.min(...xs), x1 = Math.max(...xs), z0 = Math.min(...zs), z1 = Math.max(...zs);
  return { x: (x0 + x1) / 2, z: (z0 + z1) / 2, r: Math.max(x1 - x0, z1 - z0) / 2 };
}

// Fin whale calls and tracks for one day (the whale locator places calls near the sea surface; they are drawn on the
// seafloor beneath, where the stations that heard them are). setDay(null) hides them.
export class WhaleLayer {
  constructor(scene3d, data) {
    this.data = data; this.credit = data.credit;
    this.days = Object.keys(data.days).sort();
    this.group = new THREE.Group(); this.group.visible = false; this.group.renderOrder = 7;
    scene3d.add(this.group);
    this.mats = []; this.day = null; this._built = null;
  }

  setDay(day) { this.day = day && this.data.days[day] ? day : null; this._built = null; }

  _clear() {
    for (const o of [...this.group.children]) { o.geometry.dispose(); o.material.dispose(); this.group.remove(o); }
    this.mats = [];
  }

  // Once a frame: e converts metres to world units; elevAt drapes the calls. Rebuilt when the day or e changes.
  update(e, elevAt) {
    this.group.visible = !!this.day;
    if (!this.day || this._built === `${this.day}:${e}`) return;
    this._clear();
    const { tracks, loose } = dayTracks(this.data.days[this.day]);
    const at = (lon, lat) => [toX(lon), (elevAt(lon, lat) + LIFT_M) * e, toZ(lat)];
    const pos = [], col = [], c = new THREE.Color();
    const add = (pts, hex) => { c.set(hex); for (const [lon, lat] of pts) { pos.push(...at(lon, lat)); col.push(c.r, c.g, c.b); } };
    add(loose, UNTRACKED);
    Object.entries(tracks).forEach(([id, pts]) => {
      const hex = TRACK_COLORS[(id - 1) % TRACK_COLORS.length];
      add(pts, hex);
      if (pts.length < 2) return;
      const g = new LineGeometry(); g.setPositions(smoothTrack(pts).flatMap(([lon, lat]) => at(lon, lat)));
      const m = new LineMaterial({ color: hex, linewidth: 2, transparent: true, opacity: 0.9 });
      m.resolution.set(innerWidth, innerHeight); this.mats.push(m);
      this.group.add(new Line2(g, m));
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    this.group.add(new THREE.Points(g, new THREE.PointsMaterial({ size: 4, sizeAttenuation: false, vertexColors: true, transparent: true, opacity: 0.85 })));
    this._built = `${this.day}:${e}`;
  }
}
