import { KX } from "../scene/geo.js";

export function depthScale(site, height) {
  const bottom = site.seafloor + 50;
  if (site.seafloor < 600 || !site.column.length) {
    const y = d => (d / bottom) * height;
    const step = bottom > 2000 ? 500 : bottom > 600 ? 200 : 50;
    return { y, ticks: ticks(0, bottom, step).map(d => ({ depth: d, y: y(d) })), breakAt: null };
  }
  const topEnd = 300, lowStart = Math.max(topEnd, site.seafloor - 300);
  const h1 = height * 0.3, h2 = height * 0.15, h3 = height - h1 - h2;
  const y = d => d <= topEnd ? (d / topEnd) * h1
    : d <= lowStart ? h1 + ((d - topEnd) / Math.max(1, lowStart - topEnd)) * h2
    : h1 + h2 + ((d - lowStart) / (bottom - lowStart)) * h3;
  const t = [...ticks(0, topEnd, 100), ...ticks(Math.ceil(lowStart / 100) * 100, bottom, 100)];
  return { y, ticks: [...new Set(t)].map(d => ({ depth: d, y: y(d) })), breakAt: h1 + h2 / 2 };
}
const ticks = (a, b, step) => { const out = []; for (let d = a; d <= b; d += step) out.push(d); return out; };

export function profile(site, elevAt, n = 81) {
  const halfDeg = 1 / KX;   // 1 km each way
  return Array.from({ length: n }, (_, i) => {
    const x = i / (n - 1);
    return { x, depth: -elevAt(site.lon - halfDeg + 2 * halfDeg * x, site.lat) };
  });
}

// Depth of the profile line at fraction fx (0..1) of its width, linearly interpolated.
export function profileDepthAt(prof, fx) {
  const f = Math.min(1, Math.max(0, fx)) * (prof.length - 1), i = Math.min(prof.length - 2, Math.floor(f));
  return prof[i].depth + (prof[i + 1].depth - prof[i].depth) * (f - i);
}

// The data build's water-column rule (atlas_map_data/sites.py `_in_water`). Everything else is on the
// seafloor, even when its recorded depth differs from the 45 m terrain grid by tens of meters.
const inWater = (sensor, seafloor) => Boolean(sensor.depthRange) || (sensor.depth != null && sensor.depth < seafloor - 60);

// `prof` (optional, from profile()) lets seafloor sensors follow the drawn floor line at their fanned x.
export function layout(site, sensors, familyOrder, width, height, prof = null) {
  const s = depthScale(site, height);
  const sorted = [...sensors].sort((a, b) => familyOrder[a.family] - familyOrder[b.family] || a.id.localeCompare(b.id));
  const x0 = width * 0.2, x1 = width * 0.8, n = sorted.length;
  return sorted.map((sensor, i) => {
    const x = n === 1 ? width / 2 : x0 + ((x1 - x0) * i) / (n - 1);
    if (sensor.depthRange && sensor.depthRange[0] !== sensor.depthRange[1]) {
      return { id: sensor.id, family: sensor.family, x, y: s.y(sensor.depthRange[0]), y2: s.y(sensor.depthRange[1]) };
    }
    const depth = sensor.depthRange ? sensor.depthRange[0] : sensor.depth ?? null;
    if (prof && prof.length > 1 && !inWater(sensor, site.seafloor)) {
      return { id: sensor.id, family: sensor.family, x, y: s.y(Math.max(0, profileDepthAt(prof, x / width))) };
    }
    return { id: sensor.id, family: sensor.family, x, y: s.y(depth ?? site.seafloor) };
  });
}
