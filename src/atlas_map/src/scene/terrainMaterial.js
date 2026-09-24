import * as THREE from "three";

const vert = `
  attribute float elev; attribute vec2 grad;
  attribute float drop;   // meters to lower a vertex without changing its color (tile skirts); 0 when absent
  uniform float uExag, uFlat;
  uniform sampler2D uMask; uniform float uMaskOn; uniform vec4 uMaskRect;
  varying float vElev; varying vec3 vPos; varying vec3 vN;
  // Where a finer level's tile is showing (the coverage mask), this level sinks 25 m beneath it, in 2D too.
  // Sinking rather than discarding keeps a sloped rim at the edge of the finer tiles, so a step up to this
  // level behind them is always covered (a discard left hairline cracks of background there).
  float sunk(vec2 xz) {
    if (uMaskOn < 0.5) return 0.0;
    vec2 muv = (xz - uMaskRect.xy) / (uMaskRect.zw - uMaskRect.xy);
    return muv.x >= 0.0 && muv.x <= 1.0 && muv.y >= 0.0 && muv.y <= 1.0 && texture2D(uMask, muv).r > 0.5 ? 25.0 : 0.0;
  }
  void main() {
    float s = 0.001 * uExag * (1.0 - uFlat);
    float sn = 0.001 * uExag;
    vec3 p = position; p.y = (elev - drop) * s - sunk((modelMatrix * vec4(position, 1.0)).xz) * sn;
    vElev = elev; vN = normalize(vec3(-grad.x * sn, 1.0, -grad.y * sn));
    vec4 wp = modelMatrix * vec4(p, 1.0); vPos = wp.xyz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }`;
const frag = `
  uniform float uMode, uFlat, uLines, uMute, uInterval;
  uniform vec4 uHoleA, uHoleB; uniform float uHoles;
  uniform vec4 uHoleC; uniform float uHoleCOn; uniform vec4 uClip; uniform float uClipOn;
  varying float vElev; varying vec3 vPos; varying vec3 vN;
  vec3 depthRamp(float d) {
    vec3 c0 = vec3(0.86, 0.86, 0.80), c1 = vec3(0.62, 0.71, 0.69), c2 = vec3(0.38, 0.51, 0.53),
         c3 = vec3(0.21, 0.31, 0.35), c4 = vec3(0.12, 0.16, 0.19);
    if (d < 700.0) return mix(c0, c1, d / 700.0);
    if (d < 2000.0) return mix(c1, c2, (d - 700.0) / 1300.0);
    if (d < 3000.0) return mix(c2, c3, (d - 2000.0) / 1000.0);
    return mix(c3, c4, clamp((d - 3000.0) / 1800.0, 0.0, 1.0));
  }
  bool inBox(vec4 b) { return vPos.x > b.x && vPos.x < b.y && vPos.z > b.z && vPos.z < b.w; }
  float contour(float interval, float width) {
    float v = vElev / interval; float f = abs(fract(v - 0.5) - 0.5); float w = fwidth(v) * width;
    return 1.0 - smoothstep(0.0, w, f);
  }
  void main() {
    if (uHoles > 0.5 && (inBox(uHoleA) || inBox(uHoleB))) discard;
    if (uHoleCOn > 0.5 && inBox(uHoleC)) discard;
    if (uClipOn > 0.5 && !inBox(uClip)) discard;
    vec3 n = normalize(vN);
    float shade = clamp(dot(n, normalize(vec3(-0.8, 1.0, -0.9))), 0.0, 1.0);
    float hill = mix(0.38, 1.1, shade);
    float depth = -vElev;
    vec3 base;
    if (vElev > 0.0) base = uMode < 0.5 ? mix(vec3(0.44, 0.43, 0.40), vec3(0.60, 0.59, 0.55), clamp(vElev / 900.0, 0.0, 1.0)) : vec3(0.36);
    else if (uMode < 0.5) base = depthRamp(depth);
    else base = vec3(mix(0.70, 0.16, clamp(depth / 4800.0, 0.0, 1.0)));
    vec3 col = base * hill;
    float minor = contour(uInterval, 1.0), major = contour(uInterval * 5.0, 1.5);
    float coast = step(-80.0, vElev) * step(vElev, 80.0) * contour(160.0, 1.8);
    col = mix(col, col * 0.62, (0.18 * minor + 0.4 * major) * (1.0 - uLines));
    vec3 lineCol = uMode < 0.5 ? mix(base, vec3(1.0), 0.35) : vec3(0.88);
    vec3 lineFill = (vec3(0.085) + base * 0.07) * mix(1.0, mix(0.55, 1.6, shade), 1.0 - uFlat);
    lineFill = mix(lineFill, lineCol * 0.6, minor * 0.5);
    lineFill = mix(lineFill, lineCol, major * 0.9);
    col = mix(col, lineFill, uLines);
    col = mix(col, vec3(0.93, 0.91, 0.86), coast * mix(0.5, 0.9, uLines));
    float lum = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(col, vec3(lum) * 0.5, uMute * 0.8);
    gl_FragColor = vec4(col, 1.0);
  }`;

const EMPTY = new THREE.DataTexture(new Uint8Array([0]), 1, 1, THREE.RedFormat); EMPTY.needsUpdate = true;
// extra: {holeC?: Vector4 box to discard, clip?: Vector4 box to keep, mask?: DataTexture coverage of a finer
// level (this level sinks beneath it), maskRect?: Vector4 its world rect}
export function terrainMaterial(U, interval, holes, extra = {}) {
  return new THREE.ShaderMaterial({
    vertexShader: vert, fragmentShader: frag,
    uniforms: { uExag: U.exag, uFlat: U.flat, uLines: U.lines, uMode: U.mode, uMute: U.mute,
      uInterval: { value: interval }, uHoles: { value: holes ? 1 : 0 }, uHoleA: { value: U.holeA }, uHoleB: { value: U.holeB },
      uHoleC: { value: extra.holeC ?? new THREE.Vector4() }, uHoleCOn: { value: extra.holeC ? 1 : 0 },
      uClip: { value: extra.clip ?? new THREE.Vector4() }, uClipOn: { value: extra.clip ? 1 : 0 },
      uMask: { value: extra.mask ?? EMPTY }, uMaskOn: { value: extra.mask ? 1 : 0 }, uMaskRect: { value: extra.maskRect ?? new THREE.Vector4() } },
  });
}
