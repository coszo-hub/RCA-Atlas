const LABEL = {
  OPERATIONAL: "Operating", PARTIALLY_FUNCTIONAL: "Partially functional", NOT_DEPLOYED: "Not deployed", RETIRED: "Retired",
  SUPERSEDED: "Superseded", RECOVERED: "Recovered", UNCABLED: "Uncabled", PLANNED: "Planned (COSZO)", UNKNOWN: "Status unknown",
};
const GROUP = {
  OPERATIONAL: "operating", PARTIALLY_FUNCTIONAL: "operating", NOT_DEPLOYED: "offline", RETIRED: "offline",
  SUPERSEDED: "offline", RECOVERED: "offline", UNCABLED: "offline", PLANNED: "planned", UNKNOWN: "unknown",
};
const n = v => Math.round(v).toLocaleString("en-US");

export const fmtDepth = m => (m == null ? "—" : `${n(m)} m`);
export const fmtRange = (a, b) => (a === b ? `${n(a)} m` : `${n(a)}–${n(b)} m`);
export const statusLabel = raw => LABEL[raw] ?? raw;
export const statusGroup = raw => GROUP[raw] ?? "unknown";
export const fmtDate = iso => (iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }) : "unknown date");
