import { useState } from "react";
import { files } from "../../api/gateway.js";
import Failure from "./Failure.jsx";
import { useLive } from "./useLive.js";

export default function FileBrowser({ route }) {
  const [path, setPath] = useState("");
  const f = useLive(`files:${route.instrumentKey}:${route.endpointId}:${path}`, o => files(route.instrumentKey, route.endpointId, path, o));
  const up = path.split("/").filter(Boolean).slice(0, -1).join("/");   // entry paths are relative to the endpoint root
  return (
    <div className="files">
      <div className="mono crumbs">{route.label} / {path || ""}{path && <button onClick={() => setPath(up ? `${up}/` : "")}>Up</button>}</div>
      {f.state === "loading" && <p className="muted">Listing files…</p>}
      {f.state === "error" && <Failure error={f.error} retry={f.retry} />}
      {f.state === "ok" && (<ul>{f.data.entries.map(e => (
        <li key={e.path}>{e.kind === "directory"
          ? <button onClick={() => setPath(e.path)}>{e.name}/</button>
          : <a href={e.url} target="_blank" rel="noreferrer">{e.name}</a>}</li>))}
        {/* An upstream message already explains the truncation; do not add a second, contradicting line. */}
        {f.data.message ? <li className="muted">{f.data.message}</li> : f.data.truncated && <li className="muted">Showing the newest 200 entries.</li>}</ul>)}
    </div>
  );
}
