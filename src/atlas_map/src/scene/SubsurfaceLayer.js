import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { toX, toZ } from "./geo.js";
import { countBefore, glassWindow, months, quakeArrays, surfaceArrays } from "./subsurface.js";
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
  attribute float elev; attribute float day;
  uniform float uExag, uFlat, uThrough, uShow, uPx;
  varying float vAge;
  void main() {
    vec3 p = position; p.y = elev * 0.001 * uExag * (1.0 - uFlat);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    vAge = uThrough - day;
    float fresh = 1.0 - smoothstep(0.0, 60.0, vAge);
    gl_PointSize = (vAge < 0.0 || uShow < 0.01) ? 0.0 : uPx * mix(2.0, 3.4, fresh) * clamp(14.0 / -mv.z, 0.8, 2.0);
  }`;
const quakeFrag = `
  uniform float uShow, uGhost;
  varying float vAge;
  void main() {
    if (vAge < 0.0) discard;
    if (length(gl_PointCoord - 0.5) > 0.5) discard;
    float fresh = 1.0 - smoothstep(0.0, 60.0, vAge);
    vec3 col = mix(vec3(0.66, 0.65, 0.61), vec3(1.0, 0.80, 0.52), fresh);
    gl_FragColor = vec4(col, mix(0.55, 1.0, fresh) * uShow * uGhost);
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
    return await res.json();
  } catch { return null; }
}

// Axial's subsurface in place beneath the seafloor: earthquakes, the magma chamber (AMC) top, and the caldera-wall
// faults, plus the caldera rim draped on the terrain. U.see (0..1) shows it; the terrain turns to glass above it.
export class SubsurfaceLayer {
  constructor(scene3d, U, data) {
    this.data = data; this.credit = data.credit;
    const eq = data.earthquakes, q = quakeArrays(eq);
    this.days = q.day; this.months = months(eq.day0, q.day[q.day.length - 1]);
    this.window = glassWindow(data);
    this.show = U.see; this.through = { value: this.months[this.months.length - 1].end };
    this.objects = [];
    const add = (o, order) => { o.renderOrder = order; o.frustumCulled = false; o.visible = false; scene3d.add(o); this.objects.push(o); };
    const passes = [[1, false], [GHOST, true]];

    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(q.positions, 3));
    g.setAttribute("elev", new THREE.BufferAttribute(q.elev, 1));
    g.setAttribute("day", new THREE.BufferAttribute(q.day, 1));
    for (const [alpha, ghost] of passes) {
      add(new THREE.Points(g, new THREE.ShaderMaterial({
        vertexShader: quakeVert, fragmentShader: quakeFrag, transparent: true, depthWrite: !ghost,
        depthFunc: ghost ? THREE.GreaterDepth : THREE.LessEqualDepth,
        uniforms: { uExag: U.exag, uFlat: U.flat, uThrough: this.through, uShow: U.see, uGhost: { value: alpha },
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
