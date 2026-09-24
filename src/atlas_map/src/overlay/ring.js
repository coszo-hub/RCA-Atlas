import { statusGroup } from "../data/format.js";

const GROUP_ORDER = { operating: 0, offline: 1, planned: 2, unknown: 3 };
export const ringSize = n => (n > 6 ? 30 : n > 2 ? 24 : 18);

export function ringSvg(site, sensorsById, familyByKey, size) {
  const famOrder = Object.fromEntries(Object.keys(familyByKey).map((k, i) => [k, i]));
  const sensors = site.sensorIds.map(id => sensorsById[id]).sort((a, b) =>
    famOrder[a.family] - famOrder[b.family] || GROUP_ORDER[statusGroup(a.status)] - GROUP_ORDER[statusGroup(b.status)]);
  const n = sensors.length, R = size / 2 - 2.5, cx = size / 2, gap = n > 1 ? Math.min(0.22, 1.4 / n) : 0;
  const pt = a => `${(cx + R * Math.cos(a)).toFixed(2)} ${(cx + R * Math.sin(a)).toFixed(2)}`;
  const segs = sensors.map((s, i) => {
    const g = statusGroup(s.status), col = familyByKey[s.family].color;
    const a0 = (i / n) * Math.PI * 2 - Math.PI / 2 + gap / 2, a1 = ((i + 1) / n) * Math.PI * 2 - Math.PI / 2 - gap / 2;
    const d = n === 1 ? `M ${cx - R} ${cx} a ${R} ${R} 0 1 0 ${2 * R} 0 a ${R} ${R} 0 1 0 ${-2 * R} 0`
                      : `M ${pt(a0)} A ${R} ${R} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${pt(a1)}`;
    const w = g === "operating" || g === "offline" ? 3.2 : 1.3;
    const extra = (g === "offline" ? ' opacity="0.3"' : "") + (g === "unknown" ? ' stroke-dasharray="1.6 1.4"' : "");
    return `<path class="seg" data-fam="${s.family}" d="${d}" fill="none" stroke="${col}" stroke-width="${w}"${extra}/>`;
  }).join("");
  const halo = sensors.some(s => statusGroup(s.status) === "operating")
    ? `<circle class="halo" cx="${cx}" cy="${cx}" r="${R + 4}" fill="none" stroke="#ecebe6" stroke-width="1"/>` : "";
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">${halo}` +
    `<circle cx="${cx}" cy="${cx}" r="${R + 2.2}" fill="rgba(12,12,11,0.72)"/>${segs}<circle cx="${cx}" cy="${cx}" r="1.8" fill="#ecebe6"/></svg>`;
}
