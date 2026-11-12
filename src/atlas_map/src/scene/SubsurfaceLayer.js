import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { toX, toZ } from "./geo.js";
import { FAULT_COLORS, FAULT_TYPES, countBefore, glassWindow, joinQuakes, months, quakeArrays, realtimeArrays, surfaceArrays } from "./subsurface.js";
import { atlasUrl } from "../data/bundle.js";

// Each layer draws twice. The plain pass goes first (quakes writing depth, then the translucent surfaces), and the
// terrain, glass over the subsurface, blends over it. The ghost pass comes after the terrain and draws only where
// terrain is in front, faintly, so what lies behind opaque seafloor (seen at a low angle) reads as behind it.
const ORDER = { quakes: -3, surface: -2, ghost: 4 };
const GHOST = 0.3;
const SURFACE_STYLE = {
  amc: { color: [0.80, 0.39, 0.25], fill: 0.4, line: 0.8 },            // magma: a muted ember
  wall: { color: [0.93, 0.92, 0.88], fill: 0.07, line: 0.3 },          // fault planes: glass with depth lines
};

const quakeVert = `
  attribute float elev; attribute float day; attribute float mag; attribute float fault;
  uniform float uExag, uFlat, uThrough, uShow, uPx;
  varying float vAge; varying float vFault;
  void main() {
    vec3 p = position; p.y = elev * 0.001 * uExag * (1.0 - uFlat);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    vAge = uThrough - day; vFault = fault;
    float fresh = 1.0 - smoothstep(0.0, 60.0, vAge);
    float size = mag < -9.0 ? 1.0 : clamp(0.75 + 0.3 * mag, 0.6, 1.9);   // by magnitude, where the catalog gives one
    gl_PointSize = (vAge < 0.0 || uShow < 0.01) ? 0.0 : uPx * size * mix(2.0, 3.4, fresh) * clamp(14.0 / -mv.z, 0.8, 2.0);
  }`;
const quakeFrag = `
  uniform float uShow, uGhost, uHistory, uByFault;
  uniform vec3 uFault[4];
  varying float vAge; varying float vFault;
  void main() {
    if (vAge < 0.0) discard;
    if (length(gl_PointCoord - 0.5) > 0.5) discard;
    float fresh = 1.0 - smoothstep(0.0, 60.0, vAge);
    vec3 col = mix(vec3(0.66, 0.65, 0.61), vec3(1.0, 0.80, 0.52), fresh);
    float a = mix(0.55, 1.0, fresh);
    if (uByFault > 0.5) {   // by faulting type; earthquakes with no mechanism recede
      int k = int(vFault + 0.5) - 1;
      if (k < 0) { col = vec3(0.5, 0.5, 0.48); a = 0.12; }
      else { col = k == 0 ? uFault[0] : k == 1 ? uFault[1] : k == 2 ? uFault[2] : uFault[3]; a = mix(0.8, 1.0, fresh); }
    }
    gl_FragColor = vec4(col, a * uShow * uGhost * uHistory);
  }`;

const surfVert = `
  attribute float elev;
  uniform float uExag, uFlat;
  varying float vElev; varying vec3 vPos;
  void main() {
    vec3 p = position; p.y = elev * 0.001 * uExag * (1.0 - uFlat);
    vElev = elev; vec4 wp = modelMatrix * vec4(p, 1.0); vPos = wp.xyz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }`;
const surfFrag = `
  uniform vec3 uColor; uniform float uFill, uLine, uShow, uGhost;
  varying float vElev; varying vec3 vPos;
  void main() {
    vec3 n = normalize(cross(dFdx(vPos), dFdy(vPos)));
    float shade = mix(0.55, 1.1, abs(dot(n, normalize(vec3(-0.8, 1.0, -0.9)))));
    float v = vElev / 100.0, f = abs(fract(v - 0.5) - 0.5), line = 1.0 - smoothstep(0.0, fwidth(v) * 1.2, f);
    gl_FragColor = vec4(uColor * shade, mix(uFill, uLine, line) * uShow * uGhost);
  }`;

export async function loadSubsurface(fetchImpl = fetch) {
  try {
    const res = await fetchImpl(atlasUrl("subsurface.json"));
    if (!res.ok || res.headers?.get("content-type")?.includes("html")) return null;
    const data = await res.json();
    data.unrest = await loadUnrest(fetchImpl);
    return data;
  } catch { return null; }
}

// The real-time catalog after the relocated one, monthly counts and uplift (axial_unrest.py); null when not built.
export async function loadUnrest(fetchImpl = fetch) {
  try {
    const res = await fetchImpl(atlasUrl("axial_unrest.json"));
    if (!res.ok || res.headers?.get("content-type")?.includes("html")) return null;
    const unrest = await res.json(), bin = await fetchImpl(atlasUrl(unrest.realtime.file));
    if (!bin.ok) return null;
    let buffer = await bin.arrayBuffer();
    const head = new Uint8Array(buffer, 0, 2);   // still gzip unless the server sent it with Content-Encoding
    if (head[0] === 0x1f && head[1] === 0x8b) buffer = await new Response(new Blob([buffer]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
    return { ...unrest, buffer };
  } catch { return null; }
}

// Axial's subsurface in place beneath the seafloor: earthquakes (the relocated catalog to 2021, then the real-time
// one), the magma chamber (AMC) top, and the caldera-wall faults, plus the caldera rim draped on the terrain. U.see
// (0..1) shows it; the terrain turns to glass above it.
export class SubsurfaceLayer {
  constructor(scene3d, U, data) {
    this.data = data; this.credit = data.unrest ? `${data.credit}. ${data.unrest.credit}` : data.credit;
    const eq = data.earthquakes, u = data.unrest;
    const relocated = quakeArrays(eq, u?.relocatedTypes);
    const q = u ? joinQuakes(relocated, realtimeArrays({ ...u.realtime, day0: u.day0 }, u.buffer, eq.day0)) : relocated;
    this.hasFaults = q.fault.some(f => f > 0);
    this.faultCounts = { none: 0, ...Object.fromEntries([...FAULT_TYPES].map(t => [t, 0])) };   // earthquakes of each type
    for (const f of q.fault) this.faultCounts[f > 0 ? FAULT_TYPES[f - 1] : "none"] += 1;
    this.byFault = { value: 0 };   // 1: colour by faulting type (setColorBy)
    const faultColors = { value: [...FAULT_TYPES].map(t => new THREE.Color(FAULT_COLORS[t])) };
    this.unrest = u && { ...u, buffer: undefined };
    this.day0 = eq.day0; this.days = q.day; this.months = months(eq.day0, q.day[q.day.length - 1]);
    this.window = glassWindow(data);
    this.show = U.see; this.through = { value: this.months[this.months.length - 1].end };
    this.history = { value: 1 };   // the relocated catalog fades back while an answer's live quakes are shown
    this.objects = [];
    const add = (o, order) => { o.renderOrder = order; o.frustumCulled = false; o.visible = false; scene3d.add(o); this.objects.push(o); };
    const passes = [[1, false], [GHOST, true]];

    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(q.positions, 3));
    g.setAttribute("elev", new THREE.BufferAttribute(q.elev, 1));
    g.setAttribute("day", new THREE.BufferAttribute(q.day, 1));
    g.setAttribute("mag", new THREE.BufferAttribute(q.mag, 1));
    g.setAttribute("fault", new THREE.BufferAttribute(q.fault, 1));
    for (const [alpha, ghost] of passes) {
      add(new THREE.Points(g, new THREE.ShaderMaterial({
        vertexShader: quakeVert, fragmentShader: quakeFrag, transparent: true, depthWrite: !ghost,
        depthFunc: ghost ? THREE.GreaterDepth : THREE.LessEqualDepth,
        uniforms: { uExag: U.exag, uFlat: U.flat, uThrough: this.through, uShow: U.see, uGhost: { value: alpha }, uHistory: this.history,
                    uByFault: this.byFault, uFault: faultColors,
                    uPx: { value: Math.min(devicePixelRatio, 2) } },
      })), ghost ? ORDER.ghost : ORDER.quakes);
    }

    for (const s of data.surfaces) {
      const a = surfaceArrays(s), sg = new THREE.BufferGeometry(), st = SURFACE_STYLE[s.key] ?? SURFACE_STYLE.wall;
      sg.setAttribute("position", new THREE.BufferAttribute(a.positions, 3));
      sg.setAttribute("elev", new THREE.BufferAttribute(a.elev, 1));
      sg.setIndex(new THREE.BufferAttribute(a.index, 1));
      for (const [alpha, ghost] of passes) {
        add(new THREE.Mesh(sg, new THREE.ShaderMaterial({
          vertexShader: surfVert, fragmentShader: surfFrag, transparent: true, depthWrite: false, side: THREE.DoubleSide,
          depthFunc: ghost ? THREE.GreaterDepth : THREE.LessEqualDepth,
          uniforms: { uExag: U.exag, uFlat: U.flat, uShow: U.see, uGhost: { value: alpha }, uColor: { value: new THREE.Vector3(...st.color) },
                      uFill: { value: st.fill }, uLine: { value: st.line } },
        })), ghost ? ORDER.ghost : ORDER.surface);
      }
    }

    this.rimMat = new LineMaterial({ color: 0xecebe6, linewidth: 1.2, dashed: true, dashSize: 0.12, gapSize: 0.09, transparent: true, opacity: 0 });
    this.rim = new Line2(new LineGeometry(), this.rimMat);
    add(this.rim, 6);
  }

  // Cumulative count through the end of month i.
  countThrough(i) { return countBefore(this.days, this.months[i].end); }
  setThrough(i) { this.through.value = this.months[i].end; }
  setColorBy(by) { this.byFault.value = by === "fault" ? 1 : 0; }

  // Once a frame: e converts meters to world units; elevAt drapes the rim.
  update(e, elevAt) {
    const show = this.show.value;
    for (const o of this.objects) o.visible = show > 0.001;
    this.rimMat.opacity = 0.7 * show;
    if (show > 0.001 && this._rimE !== e) {
      const arr = [];
      for (const [lon, lat] of [...this.data.rim, this.data.rim[0]]) arr.push(toX(lon), elevAt(lon, lat) * e + 0.02, toZ(lat));
      this.rim.geometry.dispose(); this.rim.geometry = new LineGeometry(); this.rim.geometry.setPositions(arr);
      this.rim.computeLineDistances(); this._rimE = e;
    }
  }
}
