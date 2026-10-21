// A fingerprint of everything a frame draws: the camera, the canvas size, and each visible object's transform,
// geometry, material and shader uniforms. The scene renders only when it changes, so an idle map costs no GPU
// time, and no layer has to remember to ask for a redraw: changing what it draws changes the fingerprint.
const f32 = new Float32Array(1), u32 = new Uint32Array(f32.buffer);
let h = 0;
const mix = v => { f32[0] = typeof v === "boolean" ? +v : v; h = Math.imul(h ^ u32[0], 16777619); };

function mixValue(v) {
  if (v == null) return;
  if (typeof v === "number" || typeof v === "boolean") return mix(v);
  if (v.isTexture) return mix(v.version);
  if (v.isColor) { mix(v.r); mix(v.g); mix(v.b); return; }
  if (v.isVector2 || v.isVector3 || v.isVector4 || v.isQuaternion) { mix(v.x); mix(v.y); mix(v.z ?? 0); mix(v.w ?? 0); return; }
  if (v.elements) { for (const e of v.elements) mix(e); return; }
  if (Array.isArray(v)) for (const x of v) mixValue(x);
}

function mixMaterial(m) {
  mix(m.id); mix(m.version); mix(m.opacity); mix(m.transparent); mix(m.visible); mix(m.depthWrite);
  if (m.uniforms) for (const k in m.uniforms) mixValue(m.uniforms[k].value);
  if (m.color) mixValue(m.color);
}

export function sceneSignature(scene, camera, width, height) {
  h = 2166136261;
  mix(width); mix(height);
  for (const e of camera.matrixWorld.elements) mix(e);
  for (const e of camera.projectionMatrix.elements) mix(e);
  scene.traverseVisible(o => {
    mix(o.id); mixValue(o.position); mixValue(o.quaternion); mixValue(o.scale); mix(o.renderOrder);
    const g = o.geometry;
    if (g) {
      mix(g.id); mix(g.drawRange.start); mix(g.drawRange.count);
      if (g.index) mix(g.index.version);
      for (const k in g.attributes) mix(g.attributes[k].version);
    }
    if (Array.isArray(o.material)) o.material.forEach(mixMaterial); else if (o.material) mixMaterial(o.material);
  });
  return h >>> 0;
}
