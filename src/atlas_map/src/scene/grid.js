import { KX, KZ, toX, toZ } from "./geo.js";

export function makeGrid(meta, arrayBuffer) {
  const { ncols, nrows, west, south, cellsize } = meta;
  const heights = new Int16Array(arrayBuffer);
  const H = (r, c) => heights[Math.min(nrows - 1, Math.max(0, r)) * ncols + Math.min(ncols - 1, Math.max(0, c))];
  const sample = (lon, lat) => {
    const fc = (lon - west) / cellsize - 0.5, fr = nrows - (lat - south) / cellsize - 0.5;
    if (fc < -0.5 || fr < -0.5 || fc > ncols - 0.5 || fr > nrows - 0.5) return null;
    const c0 = Math.floor(fc), r0 = Math.floor(fr), tc = fc - c0, tr = fr - r0;
    const top = H(r0, c0) * (1 - tc) + H(r0, c0 + 1) * tc, bottom = H(r0 + 1, c0) * (1 - tc) + H(r0 + 1, c0 + 1) * tc;
    return top * (1 - tr) + bottom * tr;
  };
  const box = [toX(west), toX(west + ncols * cellsize), toZ(south + nrows * cellsize), toZ(south)];
  return { meta, heights, H, sample, box };
}

export const stack = grids => (lon, lat) => {
  for (const g of grids) { const v = g.sample(lon, lat); if (v !== null) return v; }
  return -2500;
};

export function buildArrays(grid, smooth = 1) {
  const { ncols, nrows, west, south, cellsize } = grid.meta, H = grid.H;
  const n = ncols * nrows, dx = cellsize * KX, dz = cellsize * KZ, k = smooth;
  const positions = new Float32Array(n * 3), elev = new Float32Array(n), grad = new Float32Array(n * 2);
  for (let r = 0, i = 0; r < nrows; r++) for (let c = 0; c < ncols; c++, i++) {
    positions[i * 3] = toX(west + (c + 0.5) * cellsize);
    positions[i * 3 + 2] = toZ(south + (nrows - r - 0.5) * cellsize);
    elev[i] = grid.heights[i];
    grad[i * 2] = (H(r, c + k) - H(r, c - k)) / (2 * k * dx);
    grad[i * 2 + 1] = (H(r + k, c) - H(r - k, c)) / (2 * k * dz);   // rows run south = +z
  }
  const index = new Uint32Array((ncols - 1) * (nrows - 1) * 6);
  let q = 0;
  for (let r = 0; r < nrows - 1; r++) for (let c = 0; c < ncols - 1; c++) {
    const a = r * ncols + c, b = a + 1, d = a + ncols, e = d + 1;
    index.set([a, d, b, b, d, e], q); q += 6;
  }
  return { positions, elev, grad, index };
}
