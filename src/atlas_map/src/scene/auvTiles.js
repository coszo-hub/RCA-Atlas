import { KX, KZ, toX, toZ } from "./geo.js";

export function decode(int16, S, zScale, zOffset) {
  const m = new Float32Array(S * S);
  for (let r = 0; r < S; r++) { let acc = 0; for (let c = 0; c < S; c++) { acc += int16[r * S + c]; m[r * S + c] = acc / zScale + zOffset; } }
  return m;
}

export function wanted(levels, target, camDist, tileCenter) {
  const w = [new Set(levels[0].have), new Set(), new Set()];
  const near = (k, key, R) => { const [cx, cz] = tileCenter(k, key); return Math.hypot(cx - target.x, cz - target.z) < R; };
  if (camDist < 4) {
    const R2 = Math.min(1.2, Math.max(0.35, camDist * 0.35));
    for (const key of levels[2].have) if (near(2, key, R2)) {
      w[2].add(key);
      const [ty, tx] = key.split("_").map(Number);
      w[1].add(`${Math.floor(ty / 4)}_${Math.floor(tx / 4)}`);
    }
  }
  if (camDist < 25) {
    const R1 = Math.min(4, Math.max(1.5, camDist * 0.5));
    for (const key of levels[1].have) if (near(1, key, R1)) w[1].add(key);
  }
  return w;
}

export function tileArrays(h, S, lon0, lat0, cellDeg) {
  const dx = cellDeg * KX, dz = cellDeg * KZ, n = S * S, ring = 4 * (S - 1);
  const H = (r, c) => h[Math.min(S - 1, Math.max(0, r)) * S + Math.min(S - 1, Math.max(0, c))];
  const positions = new Float32Array((n + ring) * 3), elev = new Float32Array(n + ring),
        grad = new Float32Array((n + ring) * 2), drop = new Float32Array(n + ring);
  for (let r = 0, i = 0; r < S; r++) for (let c = 0; c < S; c++, i++) {
    positions[i * 3] = toX(lon0 + (c + 0.5) * cellDeg); positions[i * 3 + 2] = toZ(lat0 - (r + 0.5) * cellDeg);
    elev[i] = h[i];
    grad[i * 2] = (H(r, c + 1) - H(r, c - 1)) / (2 * dx); grad[i * 2 + 1] = (H(r + 1, c) - H(r - 1, c)) / (2 * dz);
  }
  const index = [];
  for (let r = 0; r < S - 1; r++) for (let c = 0; c < S - 1; c++) {
    const a = r * S + c, b = a + 1, d = a + S, e = d + 1; index.push(a, d, b, b, d, e);
  }
  const edge = [];
  for (let c = 0; c < S - 1; c++) edge.push(c);
  for (let r = 0; r < S - 1; r++) edge.push(r * S + S - 1);
  for (let c = S - 1; c > 0; c--) edge.push((S - 1) * S + c);
  for (let r = S - 1; r > 0; r--) edge.push(r * S);
  edge.forEach((v, k) => {
    const j = n + k;
    positions[j * 3] = positions[v * 3]; positions[j * 3 + 2] = positions[v * 3 + 2];
    elev[j] = elev[v]; grad[j * 2] = grad[v * 2]; grad[j * 2 + 1] = grad[v * 2 + 1]; drop[j] = 25;
  });
  for (let k = 0; k < edge.length; k++) {
    const a = edge[k], b = edge[(k + 1) % edge.length], a2 = n + k, b2 = n + ((k + 1) % edge.length);
    index.push(a, a2, b, b, a2, b2);
  }
  return { positions, elev, grad, drop, index: new Uint32Array(index) };
}

// [lon0, lat0, lon1, lat1] (west, north, east, south) that a level's tiles cover when drawn. Vertices sit at
// cell centers, so this is the tile grid shifted half a cell east and south of the survey's corner.
export function coverage(west, north, cellDeg, tileDeg, tilesX, tilesY) {
  const lon0 = west + cellDeg / 2, lat0 = north - cellDeg / 2;
  return [lon0, lat0, lon0 + tilesX * tileDeg, lat0 - tilesY * tileDeg];
}
