export function searchAtlas(bundle, query, limit = 8) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const score = fields => {
    const hay = fields.filter(Boolean).map(f => String(f).toLowerCase());
    if (hay.some(h => h.startsWith(q))) return 2;
    if (hay.some(h => h.includes(q))) return 1;
    return 0;
  };
  const out = [];
  for (const s of bundle.sites) {
    const sc = score([s.name, s.label]);
    if (sc) out.push({ kind: "site", id: s.id, title: s.name, sub: `${s.sensorIds.length} sensors`, sc: sc + 0.5 });
  }
  for (const s of bundle.sensors) {
    if (s.lat == null) continue;
    const sc = score([s.name, s.type.replaceAll("_", " "), s.refdes, s.id]);
    if (sc) out.push({ kind: "sensor", id: s.id, title: s.name, sub: bundle.siteById[s.site]?.label ?? "", sc });
  }
  return out.sort((a, b) => b.sc - a.sc || a.title.localeCompare(b.title)).slice(0, limit).map(({ sc, ...r }) => r);
}
