import { status as fetchStatus } from "../../api/gateway.js";
import { fmtDate, statusLabel } from "../../data/format.js";
import { useLive } from "./useLive.js";

export default function LiveStatus({ sensor, manifest }) {
  const live = useLive(sensor.refdes ? `status:${sensor.refdes}` : null, o => fetchStatus(sensor.refdes, o));
  const snapshot = `${statusLabel(sensor.status)}${sensor.statusSource ? ` · ${sensor.statusSource}` : ""}`;
  if (!sensor.refdes || live.state === "idle") return <div className="live-status">{snapshot}</div>;
  if (live.state === "loading") return <div className="live-status">{snapshot} · checking live…</div>;
  if (live.state === "ok") {
    const d = live.data;
    // Nereus answers live, or falls back to its snapshot when the instrument check fails; never claim both.
    const how = !d.evidenceMode || d.evidenceMode === "live" ? "checked live"
      : d.evidenceMode === "snapshot" ? "from Nereus snapshot" : `from Nereus (${d.evidenceMode})`;
    return <div className="live-status">{statusLabel(d.status ?? "UNKNOWN")} · {how}{d.data?.checkedAt ? `, data ${d.data.code} at ${new Date(d.data.checkedAt).toUTCString().slice(17, 22)} UTC` : ""}</div>;
  }
  if (live.error.kind === "unreachable") {
    return <div className="live-status degraded"><span>Live data unavailable. Showing snapshot from {fmtDate(sensor.statusAsOf ?? manifest?.corpusSnapshot)}.</span>
      <button onClick={live.retry}>Retry</button></div>;
  }
  if (live.error.kind === "notfound") {
    return <div className="live-status">{snapshot} · {live.error.source === "Nereus" ? "not tracked live by Nereus" : `${live.error.source}: ${live.error.message}`}</div>;
  }
  return <div className="live-status degraded">{snapshot} · {live.error.source} failed: {live.error.message} <button onClick={live.retry}>Retry</button></div>;
}
