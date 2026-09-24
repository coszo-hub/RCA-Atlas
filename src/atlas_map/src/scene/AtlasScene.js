import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { toX, toZ } from "./geo.js";
import { buildArrays, stack } from "./grid.js";
import { terrainMaterial } from "./terrainMaterial.js";
import { ease, isTypingTarget, moveStep, viewPose } from "./cameraMath.js";

export class AtlasScene {
  constructor(canvas, bundle, grids, { onFrame } = {}) {
    this.bundle = bundle; this.onFrame = onFrame; this.flight = null; this.held = new Set();
    this.targets = { flat: 0, lines: 0, mode: 0, mute: 0 };
    this.elevAt = stack([grids.axial, grids.hydrate, grids.overview]);
    const r = (this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true }));
    r.setPixelRatio(Math.min(devicePixelRatio, 2)); r.setSize(innerWidth, innerHeight);
    this.scene = new THREE.Scene(); this.scene.background = new THREE.Color("#121211");
    this.camera = new THREE.PerspectiveCamera(30, innerWidth / innerHeight, 0.05, 6000);
    const shrink = (b, m) => new THREE.Vector4(b[0] + m, b[1] - m, b[2] + m, b[3] - m);
    this.U = { exag: { value: 6 }, flat: { value: 0 }, lines: { value: 0 }, mode: { value: 0 }, mute: { value: 0 },
               holeA: shrink(grids.axial.box, 0.35), holeB: shrink(grids.hydrate.box, 0.35) };
    this._addTerrain(grids.overview, 100, true, 1);
    this._addTerrain(grids.axial, 50, false, 3);
    this._addTerrain(grids.hydrate, 50, false, 3);

    const c = (this.controls = new OrbitControls(this.camera, canvas));
    c.enableDamping = true; c.dampingFactor = 0.08; c.screenSpacePanning = false; c.zoomToCursor = true;
    c.maxPolarAngle = Math.PI * 0.46; c.minDistance = 2; c.maxDistance = 1400;
    // Drag moves; Ctrl/Cmd/Shift-drag rotates (OrbitControls swaps PAN→ROTATE with a modifier); right-drag rotates.
    c.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
    c.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_ROTATE };
    c.addEventListener("start", () => { this.flight = null; });
    this._onContext = e => e.preventDefault();
    canvas.addEventListener("contextmenu", this._onContext);
    this._onKeyDown = e => {
      if (!e.key.startsWith("Arrow") || isTypingTarget(e.target)) return;
      e.preventDefault(); this.held.add(e.key); this.flight = null;
    };
    this._onKeyUp = e => this.held.delete(e.key);
    this._onBlur = () => this.held.clear();
    this._onResize = () => { r.setSize(innerWidth, innerHeight); this.camera.aspect = innerWidth / innerHeight; this.camera.updateProjectionMatrix(); this.onResize?.(); };
    addEventListener("keydown", this._onKeyDown); addEventListener("keyup", this._onKeyUp);
    addEventListener("blur", this._onBlur); addEventListener("resize", this._onResize);

    this.jumpTo(bundle.overview);
    this.clock = new THREE.Clock(); this._v = new THREE.Vector3();
    this.frame = {};
    this._raf = requestAnimationFrame(this._tick);
  }

  _addTerrain(grid, interval, holes, smooth) {
    const a = buildArrays(grid, smooth);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(a.positions, 3));
    g.setAttribute("elev", new THREE.BufferAttribute(a.elev, 1));
    g.setAttribute("grad", new THREE.BufferAttribute(a.grad, 2));
    g.setIndex(new THREE.BufferAttribute(a.index, 1));
    const m = terrainMaterial(this.U, interval, holes);
    if (!holes) { m.polygonOffset = true; m.polygonOffsetFactor = -2; m.polygonOffsetUnits = -2; }
    this.scene.add(new THREE.Mesh(g, m));
  }

  get e() { return this.U.exag.value * 0.001 * (1 - this.U.flat.value); }
  yFor(lon, lat, meters) { return (meters ?? this.elevAt(lon, lat)) * this.e; }
  project(x, y, z) { const v = this._v.set(x, y, z).project(this.camera); return [(v.x + 1) / 2 * innerWidth, (1 - v.y) / 2 * innerHeight, v.z]; }

  jumpTo(view) {
    this.setExag(view.exag);
    const p = viewPose(view, this.elevAt);
    this.camera.position.set(...p.pos); this.controls.target.set(...p.target);
  }
  flyTo(view) {
    const p = viewPose(view, this.elevAt);
    this._fly(new THREE.Vector3(...p.pos), new THREE.Vector3(...p.target), view.exag, 1800);
  }
  flyToPoint(lon, lat, dist = 6) {
    const target = new THREE.Vector3(toX(lon), this.yFor(lon, lat), toZ(lat));
    const dir = this.camera.position.clone().sub(this.controls.target).normalize();
    this._fly(target.clone().add(dir.multiplyScalar(dist)), target, this.U.exag.value, 1300);
  }
  _fly(pos, target, exag, dur) {
    this.flight = { t0: performance.now(), dur, fromPos: this.camera.position.clone(), fromTarget: this.controls.target.clone(),
      fromExag: this.U.exag.value, toExag: exag, pos, target };
  }

  setExag(v) { this.U.exag.value = v; this.onExag?.(v); }
  setStyle(s) { this.targets.lines = s === "contours" ? 1 : 0; }
  setColor(c) { this.targets.mode = c === "mono" ? 1 : 0; }
  setMute(m) { this.targets.mute = m; }
  setView(v) {
    const to2d = v === "2d"; this.targets.flat = to2d ? 1 : 0;
    const sph = new THREE.Spherical().setFromVector3(this.camera.position.clone().sub(this.controls.target));
    if (to2d) this._savedPolar = sph.phi;
    sph.phi = to2d ? 0.001 : (this._savedPolar ?? 0.9);
    this.controls.minPolarAngle = 0; this.controls.maxPolarAngle = to2d ? 0.001 : Math.PI * 0.46;
    this._fly(this.controls.target.clone().add(new THREE.Vector3().setFromSpherical(sph)), this.controls.target.clone(), this.U.exag.value, 900);
  }

  _tick = () => {
    const now = performance.now(), dt = Math.min(this.clock.getDelta(), 0.05), f = this.flight;
    if (f) {
      const t = Math.min(1, (now - f.t0) / f.dur), k = ease(t);
      this.camera.position.lerpVectors(f.fromPos, f.pos, k); this.controls.target.lerpVectors(f.fromTarget, f.target, k);
      if (!f.target.equals(f.fromTarget)) this.camera.position.y += Math.sin(Math.PI * k) * f.fromPos.distanceTo(f.pos) * 0.15;
      if (f.toExag !== f.fromExag) this.setExag(f.fromExag + (f.toExag - f.fromExag) * k);
      if (t >= 1) this.flight = null;
    }
    if (this.held.size) {
      const d = moveStep(this.held, this.camera.position.toArray(), this.controls.target.toArray(), dt);
      this.camera.position.x += d[0]; this.camera.position.z += d[2];
      this.controls.target.x += d[0]; this.controls.target.z += d[2];
    }
    this.controls.update();
    for (const [key, speed] of [["flat", 5], ["lines", 6], ["mode", 8], ["mute", 8]]) {
      this.U[key].value += (this.targets[key] - this.U[key].value) * Math.min(1, dt * speed);
    }
    this.camera.updateMatrixWorld();   // overlays project with exactly this frame's camera
    const dist = this.camera.position.distanceTo(this.controls.target);
    this.frame = { dist, regionMode: dist > 160, flat: this.U.flat.value, exag: this.U.exag.value, e: this.e };
    this.onFrame?.(this);
    this.renderer.render(this.scene, this.camera);
    this._raf = requestAnimationFrame(this._tick);
  };

  dispose() {
    cancelAnimationFrame(this._raf);
    removeEventListener("keydown", this._onKeyDown); removeEventListener("keyup", this._onKeyUp);
    removeEventListener("blur", this._onBlur); removeEventListener("resize", this._onResize);
    this.renderer.domElement.removeEventListener("contextmenu", this._onContext);
    this.controls.dispose(); this.renderer.dispose();
  }
}

export async function loadGrids(meta, fetchImpl = fetch) {
  const { makeGrid } = await import("./grid.js");
  const out = {};
  await Promise.all(Object.entries(meta.grids).map(async ([name, m]) => {
    out[name] = makeGrid(m, await (await fetchImpl(`/atlas/terrain/${name}.bin`)).arrayBuffer());
  }));
  return out;
}
