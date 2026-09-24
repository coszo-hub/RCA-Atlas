import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { KX, KZ, toX, toZ } from "./geo.js";
import { approach } from "./cameraMath.js";
import { edgeChip, groupSpikes, hypoMeters, placeCard, quakePx, riseAt, sinkAt, spikeHeight } from "./evidenceMath.js";
import "./evidence.css";

// An Ask Atlas answer's evidence in the scene. Located items rise as numbered, glowing spikes from the seafloor
// (one per location); DAS cables glow with a pulse running along them; the Axial quake count's hypocentres light up
// beneath the caldera in time order. DOM (numbers, bases, halos, the card, edge chips) follows the spikes each frame.

const SINK_MS = 300, EVENT_MS = 3000, ORDER = 30;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const fmtDepth = m => (m == null ? "" : `${Math.round(m).toLocaleString("en-US")} m`);

const beamVert = `
  attribute vec2 corner;
  uniform vec3 uBase; uniform float uHeight, uWidth; uniform vec2 uRes;
  varying vec2 vC;
  void main() {
    vec4 b = projectionMatrix * viewMatrix * vec4(uBase, 1.0);
    vec4 t = projectionMatrix * viewMatrix * vec4(uBase + vec3(0.0, uHeight, 0.0), 1.0);
    vec2 d = (t.xy / t.w - b.xy / b.w) * uRes;
    float len = length(d);
    vec2 dir = len > 1e-3 ? d / len : vec2(0.0, 1.0);
    vec4 p = mix(b, t, corner.y);
    p.xy += vec2(-dir.y, dir.x) * corner.x * uWidth / uRes * p.w;   // a constant width in pixels
    gl_Position = p; vC = corner;
  }`;
const beamFrag = `
  uniform vec3 uColor; uniform float uGlow, uAlpha;
  varying vec2 vC;
  void main() {
    float x = abs(vC.x);
    float core = 1.0 - smoothstep(0.03, 0.12, x);                            // a hot line ~3 px wide
    float glow = exp(-x * x * 50.0) * 0.8 + exp(-x * x * 8.0) * 0.25;        // tight bloom, then a wide haze
    float along = pow(1.0 - vC.y, 0.7) * smoothstep(0.0, 0.04, 1.0 - vC.y);  // bright at the seafloor, fading to the tip
    vec3 col = mix(uColor * 1.25, vec3(1.0, 0.96, 0.86), core * (uGlow > 1.2 ? 0.6 : 0.3));   // the family colour, hot at the core
    gl_FragColor = vec4(col, (core * 0.95 + glow * uGlow) * along * uAlpha);
  }`;

const pointVert = `
  attribute float size, fade;
  uniform float uPx;
  varying float vFade;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mv;
    vFade = fade; gl_PointSize = size * uPx;
  }`;
const pointFrag = `
  uniform vec3 uColor;
  varying float vFade;
  void main() {
    float r = length(gl_PointCoord - 0.5) * 2.0;
    if (r > 1.0 || vFade <= 0.0) discard;
    float a = ((1.0 - smoothstep(0.0, 0.5, r)) + exp(-r * r * 4.0) * 0.5) * vFade;
    gl_FragColor = vec4(mix(uColor, vec3(1.0), (1.0 - smoothstep(0.0, 0.35, r)) * 0.7), a);
  }`;

const quakeVert = `
  attribute float elev, order, size, idx;
  uniform float uExag, uFlat, uT, uActive, uPx, uDur;
  varying float vFresh, vOn;
  void main() {
    vec3 p = position; p.y = elev * 0.001 * uExag * (1.0 - uFlat);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    float age = uT - order * uDur;
    vOn = abs(idx - uActive) < 0.5 ? 1.0 : 0.0;
    vFresh = age < 0.0 ? -1.0 : exp(-age * 2.2);
    gl_PointSize = age < 0.0 ? 0.0 : uPx * size * (1.0 + vFresh * 1.5 + vOn * 1.2);
  }`;
const quakeFrag = `
  uniform float uAlpha;
  varying float vFresh, vOn;
  void main() {
    if (vFresh < -0.5) discard;
    float r = length(gl_PointCoord - 0.5) * 2.0;
    if (r > 1.0) discard;
    float core = 1.0 - smoothstep(0.1, 0.5, r), glow = exp(-r * r * 3.0) * 0.6;
    vec3 col = mix(vec3(1.0, 0.62, 0.22), vec3(1.0, 0.95, 0.8), core);
    col = mix(col, vec3(1.0), vOn * 0.6);
    gl_FragColor = vec4(col, min(1.0, (core + glow) * (0.75 + vFresh * 0.7 + vOn * 0.5)) * uAlpha);
  }`;

const additive = { transparent: true, depthTest: false, depthWrite: false, blending: THREE.AdditiveBlending };

function densify(coords, stepKm = 0.3) {
  const out = [];
  for (let i = 0; i < coords.length - 1; i++) {
    const [a, b] = [coords[i], coords[i + 1]];
    const n = Math.max(1, Math.ceil(Math.hypot((b[0] - a[0]) * KX, (b[1] - a[1]) * KZ) / stepKm));
    for (let j = 0; j < n; j++) out.push([a[0] + (b[0] - a[0]) * j / n, a[1] + (b[1] - a[1]) * j / n]);
  }
  out.push(coords[coords.length - 1]);
  return out;
}

export class EvidenceLayer {
  // handlers: onHover(n | null), onSelect(n | null), onLive(item), onSite(item)
  constructor(container, scene, bundle, handlers = {}) {
    this.c = container; this.sc = scene; this.b = bundle; this.h = handlers;
    this.sets = [];            // the shown evidence set, plus any still sinking
    this.active = null; this.hover = null;
    this._geo = new THREE.BufferGeometry();
    this._geo.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(12), 3));
    this._geo.setAttribute("corner", new THREE.Float32BufferAttribute([-1, 0, 1, 0, -1, 1, 1, 1], 2));
    this._geo.setIndex([0, 1, 2, 2, 1, 3]);
    this.card = this._el("ev-card", "");
    this.card.style.display = "none";
    this.card.addEventListener("click", ev => {
      const b = ev.target.closest("[data-act]");
      const it = this._item(this.active);
      if (!b || !it) return;
      if (b.dataset.act === "live") this.h.onLive?.(it);
      else if (b.dataset.act === "site") this.h.onSite?.(it);
      else if (b.dataset.act === "close") this.h.onSelect?.(null);
    });
    this._last = performance.now();
  }

  _el(cls, html, parent = this.c) {
    const d = document.createElement("div"); d.className = cls; d.innerHTML = html; parent.appendChild(d); return d;
  }

  get current() { return this.sets.find(s => !s.sinkT0) ?? null; }
  _item(n) {
    const cur = this.current;
    if (n == null || !cur) return null;
    return cur.ev.located.find(x => x.n === n) ?? cur.ev.events?.find(x => x.n === n) ?? null;
  }

  // Show an answer's evidence (null clears). The previous set sinks first, then the new one rises.
  show(ev) {
    const now = performance.now(), reduced = this.sc.reducedMotion;
    let wait = 0;
    for (const s of this.sets) if (!s.sinkT0) { s.sinkT0 = now; if (s.hasItems) wait = reduced ? 0 : SINK_MS; }
    this.active = null; this.hover = null; this._renderCard();
    if (!ev) return;
    const set = { ev, t0: now + wait, spikes: [], cables: [], quakes: null };
    const { spikes, cables } = groupSpikes(ev.located);
    spikes.forEach((g, i) => set.spikes.push(this._spike(g, i)));
    cables.forEach((it, i) => set.cables.push(this._cable(it, spikes.length + i)));
    if (ev.events?.length) set.quakes = this._quakes(ev.events);
    set.hasItems = set.spikes.length + set.cables.length > 0 || !!set.quakes;
    this.sets.push(set);
  }

  clear() { this.show(null); }
  setActive(n) { this.active = n; this._renderCard(); }
  setHover(n) { this.hover = n; }

  _spike(g, i) {
    const mat = new THREE.ShaderMaterial({ vertexShader: beamVert, fragmentShader: beamFrag, ...additive, side: THREE.DoubleSide,   // the quad's winding follows the view
      uniforms: { uBase: { value: new THREE.Vector3() }, uHeight: { value: 0 }, uWidth: { value: 10 }, uRes: { value: new THREE.Vector2(innerWidth, innerHeight) },
                  uColor: { value: new THREE.Color(g.color) }, uGlow: { value: 1 }, uAlpha: { value: 1 } } });
    const mesh = new THREE.Mesh(this._geo, mat);
    mesh.frustumCulled = false; mesh.renderOrder = ORDER; this.sc.scene.add(mesh);
    const label = g.ns.length > 3 ? `${g.ns.slice(0, 2).join("·")} +${g.ns.length - 2}` : g.ns.join("·");
    const dom = {
      hit: this._el("ev-hit", ""),
      halo: this._el("ev-halo", "<i></i><i></i>"),
      base: this._el("ev-base", ""),
      tag: this._el("ev-tag", `<span>${esc(label)}</span>`),
      chip: this._el("ev-chip", `<b>${esc(label)}</b><span>${esc(g.items[0].kind === "site" ? g.items[0].site : g.items[0].code)}</span><i>→</i>`),
    };
    for (const d of Object.values(dom)) d.style.setProperty("--c", g.color);
    this._wire(dom, g.ns);
    return { ...g, i, mesh, mat, dom, label, grow: 1, vary: 0.8 + 0.4 * ((i * 0.618034) % 1) };   // varied heights keep neighbouring numbers apart
  }

  // Hover and click on any part of a spike (or its chip). A merged spike steps through its numbers on click.
  _wire(dom, ns) {
    const pick = () => (ns.includes(this.active) ? ns[(ns.indexOf(this.active) + 1) % ns.length] : ns[0]);
    for (const d of [dom.hit, dom.base, dom.tag, dom.chip].filter(Boolean)) {
      d.addEventListener("mouseenter", () => this.h.onHover?.(ns.includes(this.active) ? this.active : ns[0]));
      d.addEventListener("mouseleave", () => this.h.onHover?.(null));
      d.addEventListener("click", ev => { ev.stopPropagation(); this.h.onSelect?.(pick()); });
    }
  }

  _cable(item, i) {
    const paths = item.layers.map(id => this.b.das?.layers?.find(l => l.id === id)).filter(Boolean).map((layer, k) => {
      // Normal blending: over the pale shelf an additive glow would wash out to white.
      const flat = { color: item.color, transparent: true, depthTest: false, depthWrite: false };
      const glow = new Line2(new LineGeometry(), new LineMaterial({ ...flat, linewidth: 11, opacity: 0.3 }));
      const core = new Line2(new LineGeometry(), new LineMaterial({ ...flat, linewidth: 3, opacity: 1 }));
      const n = 22, pos = new Float32Array(n * 3), size = new Float32Array(n), fade = new Float32Array(n);
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("size", new THREE.BufferAttribute(size, 1));
      g.setAttribute("fade", new THREE.BufferAttribute(fade, 1));
      const pulse = new THREE.Points(g, new THREE.ShaderMaterial({ vertexShader: pointVert, fragmentShader: pointFrag, ...additive,
        uniforms: { uPx: { value: Math.min(devicePixelRatio, 2) }, uColor: { value: new THREE.Color(item.color) } } }));
      for (const o of [glow, core, pulse]) { o.renderOrder = ORDER - 2; o.frustumCulled = false; this.sc.scene.add(o); }
      return { lonlat: densify(layer.coords), glow, core, pulse, phase: k * 0.37, world: null };
    });
    const dom = { base: this._el("ev-base cable", ""), halo: this._el("ev-halo", "<i></i><i></i>"), tag: this._el("ev-tag", `<span>${esc(item.n)}</span>`),
      chip: this._el("ev-chip", `<b>${esc(item.n)}</b><span>${esc(item.code)}</span><i>→</i>`) };
    for (const d of Object.values(dom)) d.style.setProperty("--c", item.color);
    this._wire(dom, [item.n]);
    return { item, ns: [item.n], lon: item.lon, lat: item.lat, i, paths, dom, label: String(item.n), grow: 1 };
  }

  _quakes(events) {
    const n = events.length, pos = new Float32Array(n * 3), elev = new Float32Array(n), order = new Float32Array(n), size = new Float32Array(n), idx = new Float32Array(n);
    const datum = this.sc.subsurface?.data?.datumM;
    const t0 = Date.parse(events[0].time), span = Math.max(1, Date.parse(events[n - 1].time) - t0);
    events.forEach((e, i) => {
      pos[i * 3] = toX(e.lon); pos[i * 3 + 2] = toZ(e.lat);
      elev[i] = hypoMeters(e.depth_km, datum); order[i] = (Date.parse(e.time) - t0) / span; size[i] = quakePx(e.mag); idx[i] = i;
    });
    const g = new THREE.BufferGeometry();
    for (const [k, a, s] of [["position", pos, 3], ["elev", elev, 1], ["order", order, 1], ["size", size, 1], ["idx", idx, 1]]) g.setAttribute(k, new THREE.BufferAttribute(a, s));
    const U = this.sc.U;
    const mat = new THREE.ShaderMaterial({ vertexShader: quakeVert, fragmentShader: quakeFrag, ...additive,
      uniforms: { uExag: U.exag, uFlat: U.flat, uT: { value: 0 }, uActive: { value: -1 }, uPx: { value: Math.min(devicePixelRatio, 2) },
                  uDur: { value: EVENT_MS / 1000 }, uAlpha: { value: 1 } } });
    const pts = new THREE.Points(g, mat);
    pts.frustumCulled = false; pts.renderOrder = ORDER - 1; this.sc.scene.add(pts);
    return { pts, mat, events, halo: this._el("ev-halo quake", "<i></i><i></i>") };
  }

  _renderCard() {
    const it = this._item(this.active);
    if (!it) { this.card.style.display = "none"; this.card._n = null; return; }
    const isEvent = it.time != null;
    const title = isEvent ? `Earthquake ${it.n} · ${it.time.slice(11, 19)} UTC` : `${it.n} · ${it.label}`;
    const meta = isEvent ? [it.mag != null && `M ${(Math.abs(it.mag) < 0.05 ? 0 : it.mag).toFixed(1)}`, it.depth_km != null && `${it.depth_km.toFixed(2)} km below datum`].filter(Boolean).join(" · ")
      : it.kind === "cable" ? it.site : [it.refdes ?? it.site, fmtDepth(it.depth)].filter(Boolean).join(" · ");
    const text = !isEvent && it.excerpt ? `<p class="${it.quote ? "q" : ""}">${esc(it.quote ? `“…${it.excerpt}…”` : it.excerpt)}</p>` : "";
    const btns = [
      it.kind === "sensor" && `<button data-act="live">Live data →</button>`,
      (it.kind === "site" || (it.kind === "sensor" && it.siteId)) && `<button data-act="site">Site</button>`,
      !isEvent && it.sourceUrl && `<a href="${esc(it.sourceUrl)}" target="_blank" rel="noreferrer">Source ↗</a>`,
    ].filter(Boolean).join("");
    this.card.innerHTML = `<button class="x" data-act="close" aria-label="Close">×</button><h4>${esc(title)}</h4><div class="m">${esc(meta)}</div>${text}${btns ? `<div class="go">${btns}</div>` : ""}`;
    this.card.style.setProperty("--c", isEvent ? "#ffcc66" : it.color);
    this.card.style.display = "block"; this.card._n = it.n;
    this.card._size = null;
  }

  // The map between the side panels and above the family strip, for chips and the card. The top-row HUD only covers
  // part of the top edge, so the whole height above the strip counts (the camera's vertical inset is stricter).
  _rect() {
    const [l, r] = this.sc.insets ?? [16, 16], b = this.sc.insetsY?.[1] ?? 16;
    return { left: l, right: innerWidth - r, top: 16, bottom: innerHeight - b };
  }

  update(now = performance.now()) {
    const sc = this.sc, dt = Math.min(0.05, (now - this._last) / 1000), reduced = sc.reducedMotion, e = sc.e;
    this._last = now;
    const dist = sc.frame?.dist ?? 50, rect = this._rect(), hl = this.hover ?? this.active;
    const seafloor = (lon, lat) => Math.min(0, sc.elevAt(lon, lat)) * e;
    this._anchors = new Map();
    for (const set of [...this.sets]) {
      const t = now - set.t0, sinking = set.sinkT0 != null;
      const sink = sinking ? sinkAt(now - set.sinkT0, reduced) : 1;
      if (sinking && sink <= 0) { this._dispose(set); continue; }
      const anyOn = !sinking && hl != null && set.ev.located.some(x => x.n === hl);
      const chipsFor = [], tags = [];
      for (const s of [...set.spikes, ...set.cables]) {
        const on = !sinking && s.ns.includes(hl);
        s.grow = approach(s.grow, on ? 1.8 : 1, dt, 9, reduced);
        const rise = (sinking ? sink : riseAt(t, s.i, reduced)) || 0;
        const x = toX(s.lon), z = toZ(s.lat), y = seafloor(s.lon, s.lat);
        const [bx, by, bz] = sc.project(x, y, z);
        const front = bz < 1;
        let top = [bx, by];
        if (s.mesh) {
          const h = spikeHeight(dist) * s.grow * (on ? 1 : s.vary) * rise;
          const u = s.mat.uniforms;
          u.uBase.value.set(x, y, z); u.uHeight.value = h; u.uRes.value.set(innerWidth, innerHeight);
          u.uWidth.value = on ? 44 : 28; u.uGlow.value = on ? 1.6 : 1; u.uAlpha.value = (anyOn && !on ? 0.45 : 1) * (sinking ? sink : Math.min(1, rise * 3));
          s.mesh.visible = front && rise > 0.001;
          const p = sc.project(x, y + h, z); top = [p[0], p[1]];
        } else {
          this._updateCable(s, now, on, anyOn, sinking ? sink : Math.min(1, rise * 2), reduced, seafloor);
        }
        const shown = front && rise > 0.02, d = s.dom, dim = anyOn && !on;
        const place = (el, px, py, vis) => { el.style.transform = `translate(${px.toFixed(1)}px, ${py.toFixed(1)}px)`; el.style.opacity = vis ? (dim ? 0.55 : 1) : 0; el.style.pointerEvents = vis ? "auto" : "none"; };
        place(d.base, bx, by, shown);
        // A merged spike leads with the number in focus.
        const text = on && s.ns.length > 1 ? `${hl} +${s.ns.length - 1}` : s.label;
        if (d.tag.textContent !== text) d.tag.firstChild.textContent = text;
        tags.push({ d: d.tag, x: top[0], y: top[1], w: 12 + 7 * text.length, vis: shown && rise > 0.3, place });
        d.halo.style.transform = `translate(${bx.toFixed(1)}px, ${by.toFixed(1)}px)`; d.halo.classList.toggle("on", on && shown);
        d.tag.classList.toggle("on", on); d.base.classList.toggle("on", on);
        if (d.hit) {
          const len = Math.hypot(top[0] - bx, top[1] - by), ang = Math.atan2(top[1] - by, top[0] - bx) - Math.PI / 2;
          d.hit.style.transform = `translate(${bx.toFixed(1)}px, ${by.toFixed(1)}px) rotate(${ang.toFixed(3)}rad)`;
          d.hit.style.height = `${len.toFixed(1)}px`; d.hit.style.pointerEvents = shown ? "auto" : "none";
        }
        if (!sinking) this._anchors.set(s.ns[0], { base: [bx, by, bz], top, s });
        const chip = !sinking && rise > 0.5 ? edgeChip([bx, by, bz], rect) : null;
        d.chip.style.display = chip ? "flex" : "none";
        if (chip) chipsFor.push({ d: d.chip, chip, s });
      }
      // Numbers that would overlap stack upward, the higher one on screen keeping its place.
      tags.sort((a, b) => a.y - b.y);
      tags.forEach((t, i) => {
        for (let moved = true, n = 0; moved && n < 8; n++) {
          moved = false;
          for (const o of tags.slice(0, i)) {
            if (o.vis && t.vis && Math.abs(o.x - t.x) < (o.w + t.w) / 2 + 2 && Math.abs(o.y - t.y) < 20) { t.y = o.y - 21; moved = true; }
          }
        }
        t.place(t.d, t.x, t.y, t.vis);
      });
      // Chips on the same edge would overlap: nudge them apart along it.
      chipsFor.sort((a, b) => a.chip.y - b.chip.y || a.chip.x - b.chip.x);
      let prev = null;
      for (const c of chipsFor) {
        if (prev && Math.abs(prev.chip.x - c.chip.x) < 120 && c.chip.y - prev.chip.y < 24) c.chip.y = prev.chip.y + 24;
        const w = c.d.offsetWidth || 90;
        const x = Math.min(rect.right - w - 6, Math.max(rect.left + 6, c.chip.x - w / 2));
        c.d.style.transform = `translate(${x.toFixed(0)}px, ${(c.chip.y - 10).toFixed(0)}px)`;
        c.d.querySelector("i").style.transform = `rotate(${c.chip.angle.toFixed(3)}rad)`;
        c.d.classList.toggle("on", c.s.ns.includes(hl));
        prev = c;
      }
      set.chipsShown = chipsFor.map(c => ({ ns: c.s.ns, x: c.chip.x, y: c.chip.y }));
      if (set.quakes) this._updateQuakes(set, t, sinking ? sink : 1, hl, reduced);
    }
    this._placeCard(rect);
    const sub = sc.subsurface;
    if (sub?.history) sub.history.value = approach(sub.history.value, this.current?.quakes ? 0.15 : 1, dt, 4, reduced);
  }

  _updateCable(s, now, on, anyOn, alpha, reduced, seafloor) {
    const e = this.sc.e, lift = 0.07 + 0.022 * this.sc.U.exag.value;
    for (const p of s.paths) {
      if (!p.world || p.e !== e) {
        p.world = p.lonlat.map(([lon, lat]) => [toX(lon), seafloor(lon, lat) + lift, toZ(lat)]);
        p.cum = [0]; for (let i = 1; i < p.world.length; i++) p.cum.push(p.cum[i - 1] + Math.hypot(p.world[i][0] - p.world[i - 1][0], p.world[i][2] - p.world[i - 1][2]));
        const flat = p.world.flat();
        for (const l of [p.glow, p.core]) { l.geometry.dispose(); l.geometry = new LineGeometry(); l.geometry.setPositions(flat); }
        p.e = e;
      }
      for (const l of [p.glow, p.core]) l.material.resolution.set(innerWidth, innerHeight);
      const dim = anyOn && !on ? 0.4 : 1;
      p.glow.material.opacity = (on ? 0.42 : 0.28) * alpha * dim; p.glow.material.linewidth = on ? 16 : 11;
      p.core.material.opacity = 0.95 * alpha * dim;
      // The pulse: a bright head with a fading trail, running the route every ~3 s.
      const L = p.cum[p.cum.length - 1], pos = p.pulse.geometry.attributes.position, size = p.pulse.geometry.attributes.size, fade = p.pulse.geometry.attributes.fade;
      p.pulse.visible = !reduced && alpha > 0.05 && L > 0;
      if (!p.pulse.visible) continue;
      const head = (((now / 1000) / 3.1 + p.phase) % 1) * L * 1.15, gap = L * 0.011;
      for (let k = 0; k < pos.count; k++) {
        const d = head - k * gap, ok = d >= 0 && d <= L;
        let j = 1; while (j < p.cum.length - 1 && p.cum[j] < d) j++;
        const a = p.world[j - 1], b = p.world[j], f = ok ? (d - p.cum[j - 1]) / Math.max(1e-6, p.cum[j] - p.cum[j - 1]) : 0;
        pos.setXYZ(k, a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f + 0.01, a[2] + (b[2] - a[2]) * f);
        size.setX(k, (on ? 22 : 16) * (1 - k / pos.count * 0.75)); fade.setX(k, ok ? (1 - k / pos.count) * alpha * dim : 0);
      }
      pos.needsUpdate = size.needsUpdate = fade.needsUpdate = true;
    }
  }

  _updateQuakes(set, t, alpha, hl, reduced) {
    const q = set.quakes, u = q.mat.uniforms;
    u.uT.value = reduced ? 1e6 : Math.max(0, t / 1000); u.uAlpha.value = alpha;
    const i = hl != null && set.ev.events ? set.ev.events.findIndex(x => x.n === hl) : -1;
    u.uActive.value = i;
    const ev = i >= 0 ? set.ev.events[i] : null;
    if (ev) {
      const p = this.sc.project(toX(ev.lon), hypoMeters(ev.depth_km, this.sc.subsurface?.data?.datumM) * this.sc.e, toZ(ev.lat));
      q.halo.style.transform = `translate(${p[0].toFixed(1)}px, ${p[1].toFixed(1)}px)`;
      this._anchors.set(ev.n, { base: p, top: [p[0], p[1]] });
    }
    q.halo.classList.toggle("on", !!ev && alpha > 0.5);
  }

  _placeCard(rect) {
    const n = this.card._n;
    if (n == null) return;
    const a = this._anchors.get(n) ?? [...this._anchors.values()].find(x => x.s?.ns.includes(n));
    const off = !a || a.base[2] > 1 || a.base[0] < rect.left - 40 || a.base[0] > rect.right + 40 || a.base[1] < rect.top - 40 || a.base[1] > rect.bottom + 40;
    if (off) { this.card.style.visibility = "hidden"; return; }   // its chip points the way
    this.card.style.visibility = "visible";
    const size = (this.card._size ??= { w: this.card.offsetWidth || 280, h: this.card.offsetHeight || 130 });
    const p = placeCard([a.top[0], a.top[1] - (a.s ? 26 : 10)], a.base, size, rect);   // above the spike's number
    this.card.style.transform = `translate(${p.x.toFixed(0)}px, ${p.y.toFixed(0)}px)`;
    this.card.dataset.side = p.side;
  }

  // For the browser tests: where each spike, cable tag, chip and the card are on screen.
  snapshot() {
    const cur = this.current;
    if (!cur) return { shown: false, spikes: [], cables: [], chips: [], card: null, quakes: 0 };
    const at = el => { const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, visible: el.style.opacity !== "0" && el.style.display !== "none" }; };
    return {
      shown: true, active: this.active, hover: this.hover,
      spikes: cur.spikes.map(s => ({ ns: s.ns, kind: s.kind, height: s.mat.uniforms.uHeight.value, tag: at(s.dom.tag), base: at(s.dom.base) })),
      cables: cur.cables.map(s => ({ ns: s.ns, layers: s.item.layers, tag: at(s.dom.tag) })),
      chips: cur.chipsShown ?? [],
      card: this.card.style.display === "none" ? null : { n: this.card._n, ...at(this.card), text: this.card.textContent },
      quakes: cur.quakes?.events.length ?? 0,
    };
  }

  _dispose(set) {
    for (const s of set.spikes) { this.sc.scene.remove(s.mesh); s.mat.dispose(); }
    for (const c of set.cables) for (const p of c.paths) for (const o of [p.glow, p.core, p.pulse]) { this.sc.scene.remove(o); o.geometry.dispose(); o.material.dispose(); }
    for (const s of [...set.spikes, ...set.cables]) for (const d of Object.values(s.dom)) d.remove();
    if (set.quakes) { this.sc.scene.remove(set.quakes.pts); set.quakes.pts.geometry.dispose(); set.quakes.mat.dispose(); set.quakes.halo.remove(); }
    this.sets = this.sets.filter(s => s !== set);
  }

  dispose() { for (const s of [...this.sets]) this._dispose(s); this._geo.dispose(); this.c.innerHTML = ""; }
}
