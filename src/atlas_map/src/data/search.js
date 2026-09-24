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
    if (sc) out.push({ kind: "site", id: s.id, title: s.name, sub: s.label, located: true, sc: sc + 0.5 });
  }
  for (const s of bundle.sensors) {
    const sc = score([s.name, s.type.replaceAll("_", " "), s.refdes, s.id]);
    if (!sc) continue;
    const site = bundle.siteById[s.site]?.label, located = s.lat != null;
    // Sensors with no recorded position are found too (they open their detail without a flight), just after located ones.
    out.push({ kind: "sensor", id: s.id, title: s.name, located,
      sub: located ? site ?? "" : [site, "no recorded position"].filter(Boolean).join(" · "), sc: located ? sc : sc - 0.25 });
  }
  return out.sort((a, b) => b.sc - a.sc || a.title.localeCompare(b.title)).slice(0, limit).map(({ sc, ...r }) => r);
}
