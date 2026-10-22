import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { KX, KZ, toX, toZ } from "./geo.js";
import { buildArrays, coarsen, stack } from "./grid.js";
import { sceneSignature } from "./renderGate.js";
import { terrainMaterial } from "./terrainMaterial.js";
import { AuvLod } from "./AuvLod.js";
import { SubsurfaceLayer, loadSubsurface } from "./SubsurfaceLayer.js";
import { approach, centerShift, ease, fitDist, isMoveKey, motionDuration, moveStep, rotateSpeedFor, viewPose } from "./cameraMath.js";

export { loadGrids } from "./grid.js";

// Terrain meshes by camera distance (the controls' orbit radius): [grid step, farthest distance drawn]. The
// overview opens at 650 and the regions at 14-95. A patch's step-4 cells (about 180 m) stay under a pixel from
// 400 out, so only invisible detail is dropped; each switch has 10% hysteresis so it does not flicker.
const PATCH_LODS = [[1, 160], [2, 400], [4, Infinity]];
const OVERVIEW_LODS = [[1, 900], [2, Infinity]];
const AUV_FAR = 150;   // beyond this the 16 m summit survey hides and the GMRT grid draws the summit
const REDRAW_MS = 2000;   // an unchanged scene still redraws this often, in case something slipped the fingerprint

export class AtlasScene {
  constructor(canvas, bundle, grids, { onFrame } = {}) {
    this.bundle = bundle; this.onFrame = onFrame; this.flight = null; this.held = new Set();
    this.targets = { flat: 0, lines: 0, mode: 0, mute: 0, see: 0 }; this._view = "3d";
    this.insets = [16, 16]; this.framed = false; this._shift = [0, 0]; this._shiftTo = [0, 0];
    this._motion = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
    this.elevAt = stack([grids.axial, grids.hydrate, grids.overview]);   // until `ready` adds the AUV survey
    const r = (this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true }));
    r.setPixelRatio(Math.min(devicePixelRatio, 1.5)); r.setSize(innerWidth, innerHeight);   // 2x quadrupled the fill for no visible gain
    this.scene = new THREE.Scene(); this.scene.background = new THREE.Color("#121211");
    this.camera = new THREE.PerspectiveCamera(30, innerWidth / innerHeight, 0.05, 6000);
    const shrink = (b, m) => new THREE.Vector4(b[0] + m, b[1] - m, b[2] + m, b[3] - m);
    this.U = { exag: { value: 6 }, flat: { value: 0 }, lines: { value: 0 }, mode: { value: 0 }, mute: { value: 0 },
               see: { value: 0 }, glass: { value: new THREE.Vector3() },
               holeA: shrink(grids.axial.box, 0.35), holeB: shrink(grids.hydrate.box, 0.35) };
    // Terrain, including the MBARI 1 m Axial summit tiles when they are built. Await `ready` before
    // anything samples elevAt for good (cable, moorings, markers): the AUV survey changes the summit's heights.
    this.terrainMats = []; this.terrainLods = [];
    this.ready = (async () => {
      const sub = loadSubsurface();   // optional, like the AUV tiles: null when it is not built
      const base = stack([grids.axial, grids.hydrate, grids.overview]);
      // The GMRT grids draw first; the summit survey loads behind them (hidden until the camera is close), and
      // the Axial patch opens a hole for it only once it exists.
      this._addTerrain(grids.overview, 100, true, 1, {}, OVERVIEW_LODS);
      this._axialMat = this._addTerrain(grids.axial, 50, false, 3, { holeC: new THREE.Vector4() }, PATCH_LODS);
      this._axialMat.uniforms.uHoleCOn.value = 0;
      this._addTerrain(grids.hydrate, 50, false, 3, {}, PATCH_LODS);
      this.auv = await AuvLod.create(this.scene, this.U, terrainMaterial, undefined, base, { visible: false });   // _updateTerrain shows it up close
      if (this.auv) { this.terrainMats.push(...this.auv.mats); this._axialMat.uniforms.uHoleC.value.copy(this.auv.box); }
      this._prebuildTerrain();
      const data = await sub;
      if (data) {
        this.subsurface = new SubsurfaceLayer(this.scene, this.U, data);
        const w = this.subsurface.window;
        this.U.glass.value.set(w.x, w.z, w.r);
      }
      this.elevAt = (lon, lat) => this.auv?.sample(lon, lat) ?? base(lon, lat);
    })();

    const c = (this.controls = new OrbitControls(this.camera, canvas));
    c.enableDamping = !this.reducedMotion; c.dampingFactor = 0.08; c.screenSpacePanning = false; c.zoomToCursor = true;
    c.maxPolarAngle = Math.PI * 0.46; c.minDistance = 2; c.maxDistance = 1400;
    // Drag moves; Ctrl/Cmd/Shift-drag rotates (OrbitControls swaps PAN→ROTATE with a modifier); right-drag rotates.
    c.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
    c.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_ROTATE };
    c.addEventListener("start", () => { this.flight = null; });
    this._onContext = e => e.preventDefault();
    canvas.addEventListener("contextmenu", this._onContext);
    this._onKeyDown = e => {
      if (!isMoveKey(e)) return;
      e.preventDefault(); this.held.add(e.key); this.flight = null;
    };
    this._onKeyUp = e => (e.key === "Meta" ? this.held.clear() : this.held.delete(e.key));
    this._onBlur = () => this.held.clear();
    this._onResize = () => { r.setSize(innerWidth, innerHeight); this.camera.aspect = innerWidth / innerHeight; this._applyShift(); this._resolution(); this.onResize?.(); };
    addEventListener("keydown", this._onKeyDown); addEventListener("keyup", this._onKeyUp);
    addEventListener("blur", this._onBlur); addEventListener("resize", this._onResize);

    this.jumpTo(bundle.overview);
    this.clock = new THREE.Clock(); this._v = new THREE.Vector3();
    this.frame = {};
    this._raf = requestAnimationFrame(this._tick);
  }

  // One material per grid, shared by its distance levels; each level's mesh is built the first time it is needed.
  _addTerrain(grid, interval, holes, smooth, extra, lods) {
    const m = terrainMaterial(this.U, interval, holes, extra);
    this.terrainMats.push(m);
    if (!holes) { m.polygonOffset = true; m.polygonOffsetFactor = -2; m.polygonOffsetUnits = -2; }
    this.terrainLods.push({ grid, smooth, m, levels: lods.map(([step, far]) => ({ step, far, mesh: null })), current: -1 });
    return m;
  }

  _terrainMesh(t, level) {
    if (!level.mesh) {
      const a = buildArrays(coarsen(t.grid, level.step), Math.max(1, Math.round(t.smooth / level.step)));
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(a.positions, 3));
      g.setAttribute("elev", new THREE.BufferAttribute(a.elev, 1));
      g.setAttribute("grad", new THREE.BufferAttribute(a.grad, 2));
      g.setIndex(new THREE.BufferAttribute(a.index, 1));
      level.mesh = new THREE.Mesh(g, t.m); level.mesh.visible = false;
      this.scene.add(level.mesh);
    }
    return level.mesh;
  }

  // The levels the opening view does not use are built one at a time while the browser is idle, so zooming in
  // later does not stall on building a full-resolution mesh.
  _prebuildTerrain() {
    const later = typeof requestIdleCallback === "function" ? cb => requestIdleCallback(cb, { timeout: 4000 }) : cb => setTimeout(cb, 200);
    const next = () => {
      if (this._disposed) return;
      // Finest first: zooming in from the overview is the usual next move.
      const todo = this.terrainLods.flatMap(t => t.levels.filter(l => !l.mesh).map(l => [t, l])).sort((a, b) => a[1].step - b[1].step);
      if (!todo.length) return;
      this._terrainMesh(...todo[0]);
      later(next);
    };
    later(next);
  }

  _updateTerrain(dist) {
    for (const t of this.terrainLods) {
      let i = t.current < 0 ? t.levels.findIndex(l => dist <= l.far) : t.current;
      while (i < t.levels.length - 1 && dist > t.levels[i].far * 1.1) i++;
      while (i > 0 && dist < t.levels[i - 1].far * 0.9) i--;
      if (i === t.current) continue;
      const shown = this._terrainMesh(t, t.levels[i]);
      for (const l of t.levels) if (l.mesh) l.mesh.visible = l.mesh === shown;
      t.current = i;
    }
    if (this.auv) {
      const near = dist < AUV_FAR * (this.auv.visible ? 1.1 : 0.9);
      this.auv.setVisible(near);
      // The GMRT Axial patch leaves a hole for the survey; it closes while the survey is hidden.
      if (this._axialMat) this._axialMat.uniforms.uHoleCOn.value = near ? 1 : 0;
    }
  }

  addCable(cable) {
    const common = { transparent: true, depthTest: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -60 };
    this.mats = {
      cable: new LineMaterial({ color: 0xecebe6, linewidth: 1.5, opacity: 0.95, ...common }),
      casing: new LineMaterial({ color: 0x0b0b0a, linewidth: 3.8, opacity: 0.55, ...common }),
      approx: new LineMaterial({ color: 0xecebe6, linewidth: 1.5, opacity: 0.8, dashed: true, dashSize: 1.2, gapSize: 0.9, ...common }),
      range: new LineMaterial({ color: 0xecebe6, linewidth: 3, transparent: true, opacity: 0.95 }),
    };
    this.cableLines = [];
    for (const line of cable.lines) {
      const pts = densify(line.coords);
      for (const mat of [this.mats.casing, line.accuracy === "approximate" ? this.mats.approx : this.mats.cable]) {
        const l = new Line2(new LineGeometry(), mat);
        l.userData = { pts, info: mat === this.mats.casing ? null : line };
        l.renderOrder = mat === this.mats.casing ? 5 : 6;
        this.scene.add(l); this.cableLines.push(l);
      }
    }
    this._resolution();
    this.updateLines();
  }

  // USGS Quaternary faults, draped on the seafloor beneath the cable: solid where the trace is well constrained,
  // dashed where it is moderately constrained or inferred; the megathrust's deformation front is heavier.
  addFaults(faults) {
    const common = { transparent: true, depthTest: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -50 };
    const color = FAULT_COLOR, dash = { dashed: true, dashSize: 1.0, gapSize: 0.7 };
    this.faultMats = {
      fault: new LineMaterial({ color, linewidth: 1.5, opacity: 0.9, ...common }),
      faultDashed: new LineMaterial({ color, linewidth: 1.5, opacity: 0.8, ...dash, ...common }),
      thrust: new LineMaterial({ color, linewidth: 2.8, opacity: 0.95, ...common }),
      thrustDashed: new LineMaterial({ color, linewidth: 2.8, opacity: 0.85, ...dash, ...common }),
    };
    this.faultInfo = new Set(); this.faultLines = [];
    for (const fault of faults?.faults ?? []) {
      this.faultInfo.add(fault);
      for (const run of fault.lines) {
        const m = this.faultMats[(fault.megathrust ? "thrust" : "fault") + (run.constrained ? "" : "Dashed")];
        const l = new Line2(new LineGeometry(), m);
        l.userData = { pts: densify(run.coords, 0.5), info: fault }; l.renderOrder = 4;
        this.scene.add(l); this.faultLines.push(l);
      }
    }
    this._resolution();
    this.updateLines();
  }

  setFaultsVisible(on) { for (const l of this.faultLines ?? []) l.visible = on; }

  addDas(das) {
    const common = { transparent: true, depthTest: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -70 };
    this.dasShown = false; this.dasKinds = new Map();
    this.dasLines = (das?.layers || []).map(info => {
      this.dasKinds.set(info.kind, true);
      const mat = new LineMaterial({ color: info.color, linewidth: info.kind === "multidas" ? 4.2 : 2.7,
        opacity: 0.95, dashed: info.kind === "optodas", dashSize: 0.7, gapSize: 0.45, ...common });
      const line = new Line2(new LineGeometry(), mat);
      line.visible = false;
      line.userData = { pts: densify(info.coords), info }; line.renderOrder = 7;
      this.scene.add(line); return line;
    });
    this.updateLines();
  }

  setDasVisible(on) {
    this.dasShown = on;
    for (const line of this.dasLines ?? []) line.visible = on && this.dasKinds.get(line.userData.info.kind) !== false;
  }

  setDasKindVisible(kind, on) {
    this.dasKinds.set(kind, on);
    for (const line of this.dasLines ?? []) if (line.userData.info.kind === kind) line.visible = this.dasShown && on;
  }

  addMoorings(sites) {   // call after addCable, which creates the shared materials
    this.moorings = [];
    const mastMat = (this.mats.mast = new THREE.LineDashedMaterial({ color: 0xecebe6, transparent: true, opacity: 0.35, dashSize: 0.12, gapSize: 0.1 }));
    for (const site of sites.filter(s => s.column.length)) {
      const mast = new THREE.Line(new THREE.BufferGeometry(), mastMat);
      const ranges = site.column.map(c => { const l = new Line2(new LineGeometry(), this.mats.range); l.userData = c; this.scene.add(l); return l; });
      this.scene.add(mast); this.moorings.push({ site, mast, ranges });
    }
    this.updateLines();
  }

  updateLines() {
    const e = this.e;
    for (const l of this.cableLines ?? []) {
      const arr = [];
      for (const [lon, lat] of l.userData.pts) arr.push(toX(lon), Math.min(this.elevAt(lon, lat), 0) * e + 0.03 + 0.012 * this.U.exag.value, toZ(lat));
      l.geometry.dispose(); l.geometry = new LineGeometry(); l.geometry.setPositions(arr);
      if (l.material.dashed) l.computeLineDistances();
    }
    for (const l of this.faultLines ?? []) {
      const arr = [];
      for (const [lon, lat] of l.userData.pts) arr.push(toX(lon), Math.min(this.elevAt(lon, lat), 0) * e + 0.02 + 0.008 * this.U.exag.value, toZ(lat));
      l.geometry.dispose(); l.geometry = new LineGeometry(); l.geometry.setPositions(arr);
      if (l.material.dashed) l.computeLineDistances();
    }
    for (const l of this.dasLines ?? []) {
      const arr = [];
      for (const [lon, lat] of l.userData.pts) arr.push(toX(lon), Math.min(this.elevAt(lon, lat), 0) * e + 0.05 + 0.018 * this.U.exag.value, toZ(lat));
      l.geometry.dispose(); l.geometry = new LineGeometry(); l.geometry.setPositions(arr);
      if (l.material.dashed) l.computeLineDistances();
    }
    for (const m of this.moorings ?? []) {
      const x = toX(m.site.lon), z = toZ(m.site.lat), floorY = -m.site.seafloor * e;
      m.mast.geometry.setFromPoints([new THREE.Vector3(x, floorY, z), new THREE.Vector3(x, 0, z)]); m.mast.computeLineDistances();
      for (const r of m.ranges) {
        const c = r.userData, y0 = -c.a * e, y1 = c.a === c.b ? y0 - 0.0001 - 0.02 * this.U.exag.value : -c.b * e;
        r.geometry.dispose(); r.geometry = new LineGeometry(); r.geometry.setPositions([x, y0, z, x, y1, z]);
      }
    }
    this._lastLayout = [this.U.exag.value, this.U.flat.value];
  }

  _resolution() {
    for (const m of [...Object.values(this.mats ?? {}), ...Object.values(this.faultMats ?? {}), this.subsurface?.rimMat]) m?.resolution?.set(innerWidth, innerHeight);
  }

  get reducedMotion() { return !!this._motion?.matches; }
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
  flyToPoint(lon, lat, dist = 6, meters) {   // meters: a point below the seafloor (a hypocentre) instead of on it
    const target = new THREE.Vector3(toX(lon), this.yFor(lon, lat, meters), toZ(lat));
    const dir = this.camera.position.clone().sub(this.controls.target).normalize();
    this._fly(target.clone().add(dir.multiplyScalar(dist)), target, this.U.exag.value, 1300);
  }
  _fly(pos, target, exag, dur) {
    this.flight = { t0: performance.now(), dur: motionDuration(dur, this.reducedMotion), fromPos: this.camera.position.clone(), fromTarget: this.controls.target.clone(),
      fromExag: this.U.exag.value, toExag: exag, pos, target };
  }

  // Panels and the HUD cover the map's edges (pixels from each side); the view centers on the free area
  // between them (see centerShift). Side panels open and close on input, so that glides (unless motion is
  // reduced or `snap`); the top and bottom follow layout settling (fonts, wrapping), so they snap.
  setInsets(left, right, snap = false) {
    this.framed = true; this.insets = [left, right]; this._shiftTo[0] = centerShift(left, right);
    if (snap || this.reducedMotion) this._shift[0] = this._shiftTo[0];
    this._applyShift();
  }
  setInsetsY(top, bottom) { this.insetsY = [top, bottom]; this._shift[1] = this._shiftTo[1] = centerShift(top, bottom); this._applyShift(); }
  fit(view) { return { ...view, dist: fitDist(view.dist, innerWidth, ...this.insets) }; }
  _applyShift() { this.camera.setViewOffset(innerWidth, innerHeight, -this._shift[0], -this._shift[1], innerWidth, innerHeight); }

  setExag(v) { this.U.exag.value = v; this.onExag?.(v); }
  setStyle(s) { this.targets.lines = s === "contours" ? 1 : 0; }
  setColor(c) { this.targets.mode = c === "mono" ? 1 : 0; }
  setMute(m) { this.targets.mute = m; }
  // Show Axial's subsurface. From afar, fly in over the caldera (keeping the heading), aimed below the seafloor at
  // the middle of the layers (earthquakes 1.5-3 km deep, the magma chamber at 2.6-3.7 km) so they are in frame.
  setSubsurface(on) {
    this.targets.see = on ? 1 : 0;
    const w = this.subsurface?.window;
    if (!on || !w) return;
    this._resolution();
    const t = this.controls.target, off = this.camera.position.clone().sub(t);
    if (Math.hypot(t.x - w.x, t.z - w.z) < w.r && off.length() < w.r * 5) return;
    const exag = this.U.exag.value, dist = w.r * 3.2, polar = 0.85, az = Math.atan2(off.x, off.z);
    const target = new THREE.Vector3(w.x, -2600 * exag * 0.001, w.z);
    const pos = target.clone().add(new THREE.Vector3().setFromSphericalCoords(dist, polar, az));
    this._fly(pos, target, exag, 1800);
  }
  setQuakesThrough(i) { this.subsurface?.setThrough(i); }
  setView(v) {
    if (v === this._view) return;   // re-clicking the active view must not overwrite the saved tilt
    this._view = v;
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
      const t = f.dur > 0 ? Math.min(1, (now - f.t0) / f.dur) : 1, k = ease(t);
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
    const reduced = this.reducedMotion;
    this.controls.enableDamping = !reduced;   // no coasting after a drag under reduced motion
    this.controls.rotateSpeed = rotateSpeedFor(this.camera.position.distanceTo(this.controls.target));
    this.controls.update();
    this.auv?.update(this.controls.target, this.camera.position.distanceTo(this.controls.target), now);
    for (const [key, speed] of [["flat", 5], ["lines", 6], ["mode", 8], ["mute", 8]]) {
      this.U[key].value = approach(this.U[key].value, this.targets[key], dt, speed, reduced);
    }
    // The subsurface fades out in 2D, where everything collapses onto the seafloor plane.
    this._see = approach(this._see ?? 0, this.targets.see, dt, 5, reduced);
    this.U.see.value = this._see < 1e-3 ? 0 : this._see * Math.max(0, 1 - this.U.flat.value * 3);
    // Glass needs the terrain in the transparent pass, after the subsurface beneath it.
    const glassy = this.U.see.value > 0;
    if (glassy !== this._glassy) { this._glassy = glassy; for (const m of this.terrainMats) m.transparent = glassy; }
    this.subsurface?.update(this.e, this.elevAt);
    if (this._shift[0] !== this._shiftTo[0] || this._shift[1] !== this._shiftTo[1]) {
      this._shift = this._shift.map((v, i) => { const to = this._shiftTo[i]; return Math.abs(to - v) < 0.5 ? to : approach(v, to, dt, 10, reduced); });
      this._applyShift();
    }
    const [le, lf] = this._lastLayout ?? [];
    if (le !== this.U.exag.value || Math.abs((lf ?? 0) - this.U.flat.value) > 1e-4) this.updateLines();
    if (this.mats) {
      const colAlpha = Math.max(0, 1 - this.U.flat.value * 3);
      this.mats.range.opacity = 0.95 * colAlpha; this.mats.mast.opacity = 0.35 * colAlpha;
    }
    this.camera.updateMatrixWorld();   // overlays project with exactly this frame's camera
    const dist = this.camera.position.distanceTo(this.controls.target);
    this.frame = { dist, regionMode: dist > 160, flat: this.U.flat.value, exag: this.U.exag.value, e: this.e };
    this._updateTerrain(dist);
    this.onFrame?.(this);
    const sig = sceneSignature(this.scene, this.camera, this.renderer.domElement.width, this.renderer.domElement.height);
    if (sig !== this._sig || now - (this._drawnAt ?? 0) > REDRAW_MS) {
      this._sig = sig; this._drawnAt = now;
      this.renderer.render(this.scene, this.camera);
    }
    this._raf = requestAnimationFrame(this._tick);
  };

  dispose() {
    this._disposed = true;
    cancelAnimationFrame(this._raf);
    removeEventListener("keydown", this._onKeyDown); removeEventListener("keyup", this._onKeyUp);
    removeEventListener("blur", this._onBlur); removeEventListener("resize", this._onResize);
    this.renderer.domElement.removeEventListener("contextmenu", this._onContext);
    this.controls.dispose(); this.renderer.dispose();
  }
}

export const FAULT_COLOR = 0xff7a5c;

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
