import * as THREE from "three";
import { toX, toZ } from "./geo.js";
import { coverage, decode, tileArrays, wanted } from "./auvTiles.js";

const INTERVAL = [50, 20, 10];

const RETRY_MS = 30_000;   // a failed tile is not fetched again for this long

// Vite's SPA fallback answers a missing file with 200 text/html, so check the type and the size too (as grid.js does).
async function fetchTile(url, S, zScale, zOffset) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  if (res.headers?.get("content-type")?.includes("html")) throw new Error(`${url} is missing`);
  const buf = new Uint8Array(await res.arrayBuffer());
  const raw = buf[0] === 0x1f && buf[1] === 0x8b
    ? new Uint8Array(await new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer()) : buf;
  if (raw.byteLength !== S * S * 2) throw new Error(`${url} has ${raw.byteLength} bytes; expected ${S * S * 2}`);
  return decode(new Int16Array(raw.buffer, raw.byteOffset, S * S), S, zScale, zOffset);
}

export class AuvLod {
  static async create(scene3d, U, makeMaterial, base = "/atlas/auv/") {
    let index;
    try { const r = await fetch(base + "index.json"); if (!r.ok) return null; index = await r.json(); } catch { return null; }
    const lod = new AuvLod(scene3d, U, makeMaterial, base, index);
    try { await lod._loadBase(); } catch (err) {
      // An optional layer: without its 16 m base the summit falls back to the GMRT grid.
      for (const key of [...lod.shown[0].keys()]) lod._hide(0, key);
      console.warn(`Axial summit detail is unavailable: ${err.message}`);
      return null;
    }
    return lod;
  }

  constructor(scene3d, U, makeMaterial, base, index) {
    Object.assign(this, { scene3d, base, index, S: index.tileCells + 1, credit: index.credit, last: 0, pending: new Set(),
      cache: new Map(), cacheMax: 160, failed: new Map() });   // cache: finer levels only, LRU; failed: key -> retry time
    const { west, north } = index;
    this.levels = index.levels.map(l => ({ ...l, tileDeg: l.cellDeg * index.tileCells, have: new Set(l.tiles.map(([y, x]) => `${y}_${x}`)) }));
    this.masks = this.levels.map(L => {
      const t = new THREE.DataTexture(new Uint8Array(L.tilesX * L.tilesY), L.tilesX, L.tilesY, THREE.RedFormat);
      t.magFilter = t.minFilter = THREE.NearestFilter; t.needsUpdate = true;
      const [lon0, lat0, lon1, lat1] = coverage(west, north, L.cellDeg, L.tileDeg, L.tilesX, L.tilesY);   // where its meshes draw
      return { t, rect: new THREE.Vector4(toX(lon0), toZ(lat0), toX(lon1), toZ(lat1)) };
    });
    // Tiles draw only inside the survey: edge tiles run past it, padded with repeated edge values. The GMRT patch
    // leaves them the survey minus a 40 m rim where both draw (the GMRT wins ties), so no crack opens between them.
    const east = (this.east = west + index.nx * index.cellDeg), south = (this.south = north - index.ny * index.cellDeg), rim = 0.04;
    this.clip = new THREE.Vector4(toX(west), toX(east), toZ(north), toZ(south));
    this.box = new THREE.Vector4(this.clip.x + rim, this.clip.y - rim, this.clip.z + rim, this.clip.w - rim);
    this.mats = this.levels.map((L, k) => makeMaterial(U, INTERVAL[k], false,
      { clip: this.clip, ...(this.masks[k + 1] ? { mask: this.masks[k + 1].t, maskRect: this.masks[k + 1].rect } : {}) }));
    this.shown = this.levels.map(() => new Map());
    this.heights = new Map();
  }

  origin(L, ty, tx) { return { lon0: this.index.west + tx * L.tileDeg, lat0: this.index.north - ty * L.tileDeg }; }
  center = (k, key) => { const L = this.levels[k], [ty, tx] = key.split("_").map(Number), o = this.origin(L, ty, tx);
    return [toX(o.lon0 + L.tileDeg / 2), toZ(o.lat0 - L.tileDeg / 2)]; };

  async _geometry(k, key) {
    const ck = `${k}:${key}`;
    if (this.cache.has(ck)) { const g = this.cache.get(ck); this.cache.delete(ck); this.cache.set(ck, g); return g; }
    if (this.pending.has(ck) || this.failed.get(ck) > performance.now()) return null;
    this.pending.add(ck);
    try {
      const L = this.levels[k], [ty, tx] = key.split("_").map(Number), o = this.origin(L, ty, tx);
      const h = await fetchTile(`${this.base}L${k}/${key}.bin.gz`, this.S, this.index.zScale, this.index.zOffset);
      if (k === 0) this.heights.set(key, h);
      const a = tileArrays(h, this.S, o.lon0, o.lat0, L.cellDeg);
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(a.positions, 3));
      g.setAttribute("elev", new THREE.BufferAttribute(a.elev, 1));
      g.setAttribute("grad", new THREE.BufferAttribute(a.grad, 2));
      g.setAttribute("drop", new THREE.BufferAttribute(a.drop, 1));
      g.setIndex(new THREE.BufferAttribute(a.index, 1));
      if (k > 0) { this.cache.set(ck, g); this._evict(); }   // the 16 m base is always shown, so it stays out of the LRU
      return g;
    } catch (err) {
      this.failed.set(ck, performance.now() + RETRY_MS);
      throw err;
    } finally { this.pending.delete(ck); }
  }

  // Oldest first, skipping tiles on screen, until the cache is back under its cap.
  _evict() {
    for (const [ck, g] of this.cache) {
      if (this.cache.size <= this.cacheMax) return;
      const [k, key] = ck.split(":");
      if (this.shown[+k].has(key)) continue;
      this.cache.delete(ck); g.dispose();
    }
  }

  _setMask(k, key, on) {
    const L = this.levels[k], [ty, tx] = key.split("_").map(Number);
    this.masks[k].t.image.data[ty * L.tilesX + tx] = on ? 255 : 0; this.masks[k].t.needsUpdate = true;
  }
  _show(k, key, g) {
    if (this.shown[k].has(key)) return;
    const mesh = new THREE.Mesh(g, this.mats[k]);
    mesh.frustumCulled = false;   // heights are applied in the shader; bounds at y=0 would cull wrongly
    this.scene3d.add(mesh); this.shown[k].set(key, mesh); this._setMask(k, key, true);
  }
  _hide(k, key) {
    const mesh = this.shown[k].get(key); if (!mesh) return;
    this.scene3d.remove(mesh); this.shown[k].delete(key); this._setMask(k, key, false);
  }
  async _loadBase() { await Promise.all([...this.levels[0].have].map(async key => this._show(0, key, await this._geometry(0, key)))); }

  sample(lon, lat) {
    const L0 = this.levels[0], N = this.index.tileCells, S = this.S;
    const fx = (lon - this.index.west) / L0.cellDeg - 0.5, fy = (this.index.north - lat) / L0.cellDeg - 0.5;
    if (fx < 0 || fy < 0 || lon > this.east || lat < this.south) return null;   // edge tiles are padded past the survey
    const tx = Math.floor(fx / N), ty = Math.floor(fy / N), h = this.heights.get(`${ty}_${tx}`);
    if (!h) return null;
    const c = fx - tx * N, r = fy - ty * N, c0 = Math.floor(c), r0 = Math.floor(r), tc = c - c0, tr = r - r0;
    const at = (rr, cc) => h[Math.min(S - 1, rr) * S + Math.min(S - 1, cc)];
    return (at(r0, c0) * (1 - tc) + at(r0, c0 + 1) * tc) * (1 - tr) + (at(r0 + 1, c0) * (1 - tc) + at(r0 + 1, c0 + 1) * tc) * tr;
  }

  update(target, camDist, now) {
    if (now - this.last < 200) return;
    this.last = now;
    const want = wanted(this.levels, target, camDist, this.center);
    for (const k of [2, 1]) {
      for (const key of [...this.shown[k].keys()]) if (!want[k].has(key)) this._hide(k, key);
      const missing = [...want[k]].filter(key => !this.shown[k].has(key) && this.levels[k].have.has(key))
        .map(key => { const [cx, cz] = this.center(k, key); return [Math.hypot(cx - target.x, cz - target.z), key]; })
        .sort((a, b) => a[0] - b[0]).slice(0, Math.max(0, 6 - this.pending.size));
      for (const [, key] of missing) this._geometry(k, key).then(g => {
        // A 1 m tile waits for its 4 m parent (the next update finds it cached), so the 16 m level never shows through.
        if (g && this._parentShown(k, key) && wanted(this.levels, this._lastTarget ?? target, this._lastDist ?? camDist, this.center)[k].has(key)) this._show(k, key, g);
      }, err => console.warn(`Axial summit tile L${k}/${key} failed: ${err.message}`));
    }
    this._lastTarget = { x: target.x, z: target.z }; this._lastDist = camDist;
  }

  _parentShown(k, key) {
    if (k < 2) return true;
    const [ty, tx] = key.split("_").map(Number);
    return this.shown[1].has(`${Math.floor(ty / 4)}_${Math.floor(tx / 4)}`);
  }

  finest() { return this.shown[2].size ? "1 m" : this.shown[1].size ? "4 m" : "16 m"; }
  stats() { return { L0: this.shown[0].size, L1: this.shown[1].size, L2: this.shown[2].size }; }
}
