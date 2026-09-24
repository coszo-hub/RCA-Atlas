import { fromX, fromZ, toX, toZ } from "../scene/geo.js";
import { occluded } from "../scene/occlusion.js";
import { fmtDepth, fmtRange } from "../data/format.js";
import { nearest } from "./cableHover.js";
import { place } from "./labels.js";
import { ringSize, ringSvg } from "./ring.js";
import "./overlay.css";

const PLACES = [{ t: "Newport", lon: -124.05, lat: 44.63 }, { t: "Pacific City", lon: -123.96, lat: 45.2 }];

export class OverlayLayer {
  constructor(container, bundle, scene, handlers) {
    this.c = container; this.b = bundle; this.scene = scene; this.h = handlers; this.focus = new Set(); this.selected = null;
    const el = (cls, html) => { const d = document.createElement("div"); d.className = cls; d.innerHTML = html; container.appendChild(d); return d; };
    const located = bundle.sensors.filter(s => s.lat != null);
    this.regions = bundle.regions.filter(r => located.some(s => s.region === r.key)).map(r => {
      const ss = located.filter(s => s.region === r.key);
      const lon = ss.reduce((a, s) => a + s.lon, 0) / ss.length, lat = ss.reduce((a, s) => a + s.lat, 0) / ss.length;
      const d = el("rlabel", `<div class="card"><b>${r.label}</b><span class="mono">${ss.length}</span></div><div class="stem"></div><div class="foot"></div>`);
      d.onclick = () => handlers.onRegionClick?.(r.key);
      return { d, lon, lat };
    });
    this.sites = bundle.sites.map(site => {
      const size = ringSize(site.sensorIds.length);
      const d = el("site", ringSvg(site, bundle.sensorById, bundle.familyByKey, size) +
        `<div class="name">${site.label}<span class="mono">${site.sensorIds.length}</span></div>`);
      d.setAttribute("role", "button"); d.setAttribute("aria-label", `${site.name}, ${site.sensorIds.length} sensors`); d.tabIndex = 0;
      d.onmouseenter = ev => handlers.onSiteHover?.(site, ev); d.onmousemove = ev => handlers.onSiteHover?.(site, ev);
      d.onmouseleave = () => handlers.onSiteHover?.(site, null);
      d.onclick = () => handlers.onSiteClick?.(site);
      d.onkeydown = ev => { if (ev.key === "Enter") handlers.onSiteClick?.(site); };
      return { site, d, name: d.querySelector(".name"), size, inFocus: true };
    });
    this.columns = bundle.sites.filter(s => s.column.length).map(site => ({ site, d: el("clabel",
      `<div class="surface">Sea surface <span class="mono">0 m</span></div>` +
      site.column.map(c => `<div>${c.kind} <span class="mono">${fmtRange(c.a, c.b)}</span></div>`).join("") +
      `<div class="floor">Seafloor <span class="mono">${fmtDepth(site.seafloor)}</span></div>`) }));
    this.nodes = bundle.cable.nodes.map(node => {
      const d = el("pnode", `<i></i><span class="mono">${node.code}</span>`);
      d.onmouseenter = ev => handlers.onNodeHover?.(node, ev); d.onmousemove = ev => handlers.onNodeHover?.(node, ev);
      d.onmouseleave = () => handlers.onNodeHover?.(node, null); d.onclick = () => handlers.onNodeClick?.(node);
      return { node, d, code: d.querySelector("span") };
    });
    this.places = PLACES.map(p => ({ ...p, d: el("place", p.t) }));
    this._onMove = ev => {
      if (ev.buttons) return;
      const lines = (scene.cableLines ?? []).filter(l => l.userData.info && l.userData.proj).map(l => ({ info: l.userData.info, pts: l.userData.proj }));
      const hit = nearest(ev.clientX, ev.clientY, lines);
      scene.renderer.domElement.style.cursor = hit ? "help" : "";
      handlers.onCableHover?.(hit, hit ? ev : null);
    };
    scene.renderer.domElement.addEventListener("pointermove", this._onMove);
  }

  setFocus(focus) {
    this.focus = focus;
    for (const s of this.sites) {
      for (const seg of s.d.querySelectorAll("path.seg")) seg.style.opacity = focus.size && !focus.has(seg.dataset.fam) ? 0.07 : "";
      s.inFocus = !focus.size || s.site.sensorIds.some(id => focus.has(this.b.sensorById[id].family));
    }
  }

  setSelected(id) { this.selected = id; for (const s of this.sites) s.d.classList.toggle("selected", s.site.id === id); }

  update() {
    const sc = this.scene, { dist, regionMode, e, flat } = sc.frame, cam = sc.camera.position.toArray();
    const ground = (x, z) => Math.min(0, sc.elevAt(fromX(x), fromZ(z))) * e;
    for (const r of this.regions) {
      const [x, y, z] = sc.project(toX(r.lon), sc.yFor(r.lon, r.lat) + 0.3, toZ(r.lat));
      Object.assign(r.d.style, { left: `${x}px`, top: `${y + 3}px`, opacity: regionMode && z < 1 ? 1 : 0, pointerEvents: regionMode ? "auto" : "none" });
    }
    const labelItems = [];
    for (const s of this.sites) {
      const px = toX(s.site.lon), py = -s.site.seafloor * e, pz = toZ(s.site.lat);
      const [x, y, z] = sc.project(px, py, pz);
      const onScreen = !regionMode && z < 1 && x > -40 && x < innerWidth + 40 && y > -40 && y < innerHeight + 40;
      s.hidden = onScreen && occluded(cam, [px, py + 0.01, pz], ground);
      const vis = onScreen && !s.hidden;
      Object.assign(s.d.style, { left: `${x}px`, top: `${y}px`, opacity: onScreen ? (s.hidden ? 0.12 : s.inFocus ? 1 : 0.25) : 0, pointerEvents: vis ? "auto" : "none" });
      if (vis && s.inFocus) labelItems.push({ id: s.site.id, x: x - s.size / 2, y, w: s.size + 12 + s.site.label.length * 6.4, h: 18, priority: s.site.sensorIds.length });
      s._x = x; s._y = y;
    }
    const shown = place(labelItems);
    for (const s of this.sites) s.name.style.opacity = shown.has(s.site.id) ? 1 : 0;
    const colAlpha = Math.max(0, 1 - flat * 3);
    for (const c of this.columns) {
      const px = toX(c.site.lon), pz = toZ(c.site.lat), [x, y, z] = sc.project(px, 0, pz);
      const show = colAlpha > 0.5 && !regionMode && z < 1 && dist < 90 && !occluded(cam, [px, 0, pz], ground);
      Object.assign(c.d.style, { left: `${x}px`, top: `${y}px`, opacity: show ? 1 : 0 });
    }
    for (const n of this.nodes) {
      const [x, y, z] = sc.project(toX(n.node.lon), Math.min(sc.elevAt(n.node.lon, n.node.lat), 0) * e + 0.05, toZ(n.node.lat));
      Object.assign(n.d.style, { left: `${x}px`, top: `${y}px`, opacity: z < 1 ? (regionMode ? 0.75 : 0.9) : 0 });
      n.code.style.opacity = regionMode ? 1 : 0;
    }
    for (const p of this.places) {
      const [x, y, z] = sc.project(toX(p.lon), 0.3, toZ(p.lat));
      Object.assign(p.d.style, { left: `${x}px`, top: `${y}px`, opacity: z < 1 ? 1 : 0 });
    }
    for (const l of sc.cableLines ?? []) {
      if (!l.userData.info) continue;
      l.userData.proj = l.userData.pts.filter((_, i) => i % 3 === 0).map(([lon, lat]) =>
        sc.project(toX(lon), Math.min(sc.elevAt(lon, lat), 0) * e, toZ(lat)));
    }
  }

  dispose() { this.scene.renderer.domElement.removeEventListener("pointermove", this._onMove); this.c.innerHTML = ""; }
}
