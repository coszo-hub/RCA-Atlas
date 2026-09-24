import { useCallback, useEffect, useState } from "react";

const blank = key => ({ key, state: key ? "loading" : "idle", data: null, error: null });

// Fetch keyed live data; a response for an old key never lands under a new one.
// State carries the key it belongs to, so even the first render after a key change
// shows "loading" rather than the previous key's data. Each request also has its own
// liveness flag, so a response that ignores the abort is dropped after a key change or retry.
export function useLive(key, fetcher) {
  const [s, setS] = useState(() => blank(key));
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    setS(blank(key));
    if (!key) return;
    let alive = true;
    const ctrl = new AbortController();
    fetcher({ signal: ctrl.signal }).then(r => {
      if (!alive) return;
      setS(r.ok ? { key, state: "ok", data: r.data, error: null } : { key, state: "error", data: null, error: r });
    }, err => {
      if (alive && err?.name !== "AbortError") setS({ key, state: "error", data: null, error: { kind: "unreachable", source: "gateway", message: String(err) } });
    });
    return () => { alive = false; ctrl.abort(); };
  }, [key, nonce]);   // eslint-disable-line react-hooks/exhaustive-deps -- the key identifies the request
  const retry = useCallback(() => setNonce(n => n + 1), []);
  const { key: _k, ...view } = s.key === key ? s : blank(key);
  return { ...view, retry };
}
