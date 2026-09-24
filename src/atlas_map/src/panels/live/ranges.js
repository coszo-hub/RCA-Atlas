const iso = d => d.toISOString().replace(/\.\d{3}Z$/, "Z");
const MAX_MS = 31 * 24 * 3600 * 1000;

// Presets end at the dataset's newest reading when that is earlier than now: most OOI ERDDAP datasets refresh
// about once a day, so a window ending now would usually be empty.
export function preset(key, now = new Date(), dataEnd = null) {
  const last = dataEnd ? new Date(dataEnd) : null;
  const end = new Date(last && !isNaN(last) && last < now ? last : now); end.setUTCSeconds(0, 0);
  const ms = { "24h": 864e5, "7d": 7 * 864e5, "30d": 30 * 864e5 }[key];
  return { start: iso(new Date(end - ms)), end: iso(end) };
}

// datetime-local values ("YYYY-MM-DDTHH:MM") are read as UTC, like every other time in the atlas.
export function checkCustom(startLocal, endLocal) {
  const s = new Date(`${startLocal}:00Z`), e = new Date(`${endLocal}:00Z`);
  if (isNaN(s) || isNaN(e)) return { ok: false, message: "Enter both times." };
  if (e <= s) return { ok: false, message: "End must be after start." };
  if (e - s > MAX_MS) return { ok: false, message: "Ranges are limited to 31 days per request. Pick a shorter range or download the data from ERDDAP." };
  return { ok: true, start: iso(s), end: iso(e) };
}
