import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { isTypingTarget } from "../scene/cameraMath.js";
import { resolveEvidence, tourOf } from "../evidence/resolve.js";
import { MinButton } from "../ui/Minimize.jsx";
import { MODELS, askAtlas, modelLabel } from "./askApi.js";
import { parseAnswer } from "./answerText.js";
import "./ask.css";

const KEY = "atlas.chat.open";
export const askStartsOpen = () => localStorage.getItem(KEY) !== "false";

// The demo script: a site's instruments, a measurement across the array, data access, and the live quake count.
export const SUGGESTIONS = [
  "What instruments are on Southern Hydrate Ridge?",
  "Which instruments measure dissolved oxygen?",
  "How do I get the DAS data?",
  "How many earthquakes at Axial today?",
];

const DOC_COLOR = "#8d8b84";
const fmtDepth = m => (m == null ? "—" : `${Math.round(m).toLocaleString("en-US")} m`);
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const utc = iso => iso.slice(11, 19);
export const fmtMag = m => (m == null ? "—" : `M ${(Math.abs(m) < 0.05 ? 0 : m).toFixed(1)}`);   // no "M -0.0"
const fmtKm = km => (km == null ? "—" : `${km.toFixed(2)} km`);
// The active quake's second line: its full time, magnitude, depth, and position.
const quakeLine = q => [`${q.time.slice(0, 10)} ${utc(q.time)} UTC`, fmtMag(q.mag), q.depth_km != null && `${fmtKm(q.depth_km)} below datum`,
  `${q.lat.toFixed(3)}° N, ${Math.abs(q.lon).toFixed(3)}° W`].filter(Boolean).join(" · ");
// Keys typed into a field, a select, a slider or editable text stay there.
const ownsKeys = el => isTypingTarget(el) || !!el?.closest?.('[role="slider"], [contenteditable="true"]');

function stats(e) {
  const { ev, data, ms } = e, secs = `${(ms / 1000).toFixed(1)} s`, model = modelLabel(data.answer_model);
  if (ev.count) return [ev.count.n != null && plural(ev.count.n, "earthquake"), ev.count.day && `${ev.count.day} UTC`, secs, model].filter(Boolean).join(" · ");
  return [`${ev.located.length} on the map`, plural(ev.documents.length, "document"), secs, model].filter(Boolean).join(" · ");
}

// Ask Atlas: the left sidebar. The thread of questions and answers; the shown answer's evidence is on the map
// (App owns which, and the active and hovered numbers, shared with the evidence layer). ← / → tour that evidence
// once one item is active, also while a side panel is open (each step opens the next station). Escape clears the
// active item, then the evidence; while a side panel is open it is the panel's (back from a sensor, then close).
export default function AskPanel({ bundle, evidence, activeN, hoverN, panelOpen = false, onShow, onHover, onSelect, onOpenChange }) {
  const [open, setOpen] = useState(askStartsOpen);
  const [entries, setEntries] = useState([]), [draft, setDraft] = useState(""), [model, setModel] = useState("auto");
  const busy = entries.some(e => e.status === "pending");
  const threadRef = useRef(null), abortRef = useRef(null), nextId = useRef(1);

  // Before paint, so the top row starts beside the panel instead of sliding over from the edge on load.
  useLayoutEffect(() => {
    localStorage.setItem(KEY, String(open));
    const root = document.documentElement.style;
    root.setProperty("--left-inset", open ? "412px" : "16px");
    root.setProperty("--strip-reserve", open ? "0px" : "132px");   // the family strip keeps clear of the minimized tab
    onOpenChange?.(open);
  }, [open, onOpenChange]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const run = async (id, q, m) => {
    abortRef.current?.abort();
    const ctl = (abortRef.current = new AbortController());
    let r;
    try { r = await askAtlas(q, { model: m, signal: ctl.signal }); } catch { return; }   // aborted: a newer question took over
    const ev = r.ok ? { id, ...resolveEvidence(r.data, bundle) } : null;
    setEntries(list => list.map(e => (e.id !== id ? e : r.ok ? { ...e, status: "ok", data: r.data, ms: r.ms, ev } : { ...e, status: "error", message: r.message })));
    if (ev) onShow(ev);
  };
  const ask = question => {
    const q = question.trim();
    if (q.length < 2 || busy) return;
    const id = nextId.current++;
    setEntries(list => [...list, { id, q, model, status: "pending" }]);
    setDraft("");
    run(id, q, model);
  };
  const retry = e => { setEntries(list => list.map(x => (x.id === e.id ? { ...x, status: "pending" } : x))); run(e.id, e.q, e.model); };

  // The newest question scrolls into view (its headline at the top) when asked and when answered.
  const last = entries[entries.length - 1];
  useEffect(() => {
    const el = threadRef.current?.querySelector(`[data-entry="${last?.id}"]`);
    el?.scrollIntoView?.({ block: "start", behavior: "smooth" });
  }, [last?.id, last?.status]);

  // The tour: the shown evidence in order (located items, or the quake events).
  const tour = useMemo(() => tourOf(evidence), [evidence]);
  const step = d => {
    if (!tour.length) return;
    const i = tour.findIndex(x => x.n === activeN);
    onSelect(tour[i < 0 ? (d > 0 ? 0 : tour.length - 1) : (i + d + tour.length) % tour.length].n);
  };
  const keys = useRef();
  keys.current = { evidence, activeN, panelOpen, step, onSelect, onShow };
  useEffect(() => {
    // Capture, so a tour step does not also pan the map (the scene listens for arrows on window, after this).
    const onKey = e => {
      const k = keys.current;
      if (!k.evidence || e.metaKey || e.ctrlKey || e.altKey) return;
      const composerEmpty = e.target?.dataset?.askComposer != null && !e.target.value;
      if (ownsKeys(e.target) && !composerEmpty) return;
      if (e.key === "Escape") { if (k.panelOpen) return; if (k.activeN != null) k.onSelect(null); else k.onShow(null); return; }
      if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && k.activeN != null) {
        e.preventDefault(); e.stopPropagation();
        k.step(e.key === "ArrowRight" ? 1 : -1);
      }
    };
    addEventListener("keydown", onKey, true);
    return () => removeEventListener("keydown", onKey, true);
  }, []);

  if (!open) return <button className="ask-tab panel" aria-label="Open Ask Atlas" onClick={() => setOpen(true)}>Ask Atlas</button>;
  const hl = hoverN ?? activeN;
  return (
    <aside className="panel ask" aria-label="Ask Atlas">
      <div className="ask-head"><span>Ask Atlas</span><span className="ask-head-r">RCA · COSZO<MinButton label="Ask Atlas" onClick={() => setOpen(false)} /></span></div>
      <div className="ask-thread" ref={threadRef} aria-live="polite">
        {entries.length === 0 && (
          <div className="ask-empty">
            <p>Ask about the Regional Cabled Array and COSZO. Answers cite their sources, and the map shows where that evidence was measured.</p>
            <div className="ask-label"><span>Try</span></div>
            {SUGGESTIONS.map(s => <button key={s} className="ask-suggest" onClick={() => ask(s)}>{s}</button>)}
          </div>
        )}
        {entries.map(e => (
          <Entry key={e.id} e={e} shown={evidence?.id === e.id && e.status === "ok"} hl={hl} activeN={activeN} tour={tour}
            onShow={onShow} onHover={onHover} onSelect={onSelect} onStep={step} onRetry={() => retry(e)} />
        ))}
      </div>
      <form className="ask-composer" onSubmit={e => { e.preventDefault(); ask(draft); }}>
        <textarea data-ask-composer="" aria-label="Ask a question" rows="1" value={draft}
          placeholder={entries.length ? "Ask a follow-up…" : "Ask the Atlas…"} onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); ask(draft); } }} />
        <label className="ask-model"><span className="sr-only">Answer model</span>
          <select aria-label="Answer model" value={model} onChange={e => setModel(e.target.value)}>
            {MODELS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </label>
        <button type="submit" aria-label="Ask" disabled={busy}>↵</button>
      </form>
    </aside>
  );
}

function Entry({ e, shown, hl, activeN, tour, onShow, onHover, onSelect, onStep, onRetry }) {
  const ev = e.ev;
  const byN = useMemo(() => new Map([...(ev?.located ?? []).map(x => [x.n, x]), ...(ev?.documents ?? []).map(d => [d.n, { ...d, doc: true }])]), [ev]);
  const blocks = useMemo(() => (e.data ? parseAnswer(e.data.answer, new Set(byN.keys())) : []), [e.data, byN]);
  const live = shown;   // only the answer on the map is interactive; an earlier one shows its evidence on click
  const pos = tour.findIndex(x => x.n === activeN);
  const hover = n => live && onHover(n);
  // Stepping keeps the active row and its details in view (the quake list scrolls on its own).
  const ref = useRef(null);
  useEffect(() => {
    if (!live || activeN == null) return;
    for (const el of ref.current?.querySelectorAll("tr.active, tr.active + tr.ex") ?? []) el.scrollIntoView?.({ block: "nearest" });
  }, [live, activeN]);
  const cite = (n, i, to) => {
    if (to) {
      // A range ([1-15]) is one superscript that stands for its first number (the first on the map, if any is).
      const ns = Array.from({ length: to - n + 1 }, (_, k) => n + k), lead = ns.find(k => !byN.get(k).doc) ?? n, it = byN.get(lead);
      return <sup key={i}><button className={`cite${live && ns.includes(hl) ? " on" : ""}`} style={{ "--c": it.doc ? DOC_COLOR : it.color }}
        aria-label={`Sources ${n}–${to}: ${it.label ?? it.title} and others`} onMouseEnter={() => hover(lead)} onMouseLeave={() => hover(null)}
        onClick={() => live && !it.doc && onSelect(lead)}>{n}–{to}</button></sup>;
    }
    const it = byN.get(n), on = live && hl === n;
    if (it.doc) return <sup key={i}><a className={`cite${on ? " on" : ""}`} style={{ "--c": DOC_COLOR }} href={it.url || undefined} target="_blank" rel="noreferrer"
      aria-label={`Source ${n}: ${it.title}`} onMouseEnter={() => hover(n)} onMouseLeave={() => hover(null)}>{n}</a></sup>;
    return <sup key={i}><button className={`cite${on ? " on" : ""}`} style={{ "--c": it.color }} aria-label={`Source ${n}: ${it.label}`}
      onMouseEnter={() => hover(n)} onMouseLeave={() => hover(null)} onClick={() => live && onSelect(n)}>{n}</button></sup>;
  };
  const inline = parts => parts.map((p, i) => (p.t === "cite" ? cite(p.n, i, p.to) : p.t === "b" ? <strong key={i}>{p.v}</strong> : <Fragment key={i}>{p.v}</Fragment>));
  const row = (n, cells, color, extra) => {
    const on = live && hl === n, active = live && activeN === n;
    return (
      <Fragment key={n}>
        <tr className={`${on ? "on" : ""}${active ? " active" : ""}`} style={{ "--c": color }} tabIndex={live ? 0 : -1}
          onMouseEnter={() => hover(n)} onMouseLeave={() => hover(null)} onClick={() => live && onSelect(n)}
          onKeyDown={k => { if (live && (k.key === "Enter" || k.key === " ")) { k.preventDefault(); onSelect(n); } }}>
          <td className="i">{n}</td>{cells}
        </tr>
        {active && extra && <tr className="ex"><td /><td colSpan={3}>{extra}</td></tr>}
      </Fragment>
    );
  };
  const stepper = live && tour.length > 0 && (
    <span className="ask-step">
      <button aria-label="Previous evidence" onClick={() => onStep(-1)}>←</button>
      <span className="mono">{pos < 0 ? "–" : pos + 1} / {tour.length}</span>
      <button aria-label="Next evidence" onClick={() => onStep(1)}>→</button>
    </span>
  );

  return (
    <article ref={ref} className={`ask-entry${live || e.status !== "ok" ? "" : " past"}`} data-entry={e.id}
      onClick={k => { if (e.status === "ok" && !live && !k.target.closest("a, button")) onShow(ev); }}>
      <h2 className="ask-q">{e.status === "ok" && !live
        ? <button className="ask-reshow" aria-label={`Show the evidence for: ${e.q}`} onClick={() => onShow(ev)}>{e.q}</button> : e.q}</h2>
      {e.status === "ok" && <div className="ask-stats mono">{stats(e)}</div>}
      {e.status === "pending" && <p className="ask-wait">Reading the corpus…</p>}
      {e.status === "error" && <p className="ask-error">{e.message} <button onClick={onRetry}>Retry</button></p>}
      {e.status === "ok" && (
        <>
          <div className="ask-answer">
            {blocks.map((b, i) => (b.type === "h" ? <h3 key={i}>{inline(b.parts)}</h3>
              : b.type === "li" ? <p key={i} className={`li l${b.level}`}>{inline(b.parts)}</p> : <p key={i}>{inline(b.parts)}</p>))}
          </div>
          {ev.located.length > 0 && (
            <>
              <div className="ask-label"><span id={`ev-${e.id}`}>Evidence on the map</span>{stepper}</div>
              <table className="ask-table" aria-labelledby={`ev-${e.id}`}>
                <thead><tr><th>#</th><th>Instrument</th><th>Site</th><th className="r">Depth</th></tr></thead>
                <tbody>{ev.located.map(x => row(x.n, <><td className={x.kind === "site" ? "k-site" : undefined}>{x.kind === "site" ? "site" : x.code}</td><td>{x.site}</td><td className="r">{fmtDepth(x.depth)}</td></>, x.color,
                  x.excerpt && (x.quote ? <q>{x.excerpt}</q> : x.excerpt)))}</tbody>
              </table>
            </>
          )}
          {ev.events && (
            <>
              <div className="ask-label"><span id={`ev-${e.id}`}>Earthquakes on the map</span>{stepper}</div>
              <div className="ask-scroll">
                <table className="ask-table" aria-labelledby={`ev-${e.id}`}>
                  <thead><tr><th>#</th><th>Time UTC</th><th>Mag</th><th className="r">Depth</th></tr></thead>
                  <tbody>{ev.events.map(q => row(q.n, <><td>{utc(q.time)}</td><td>{fmtMag(q.mag)}</td>
                    <td className="r">{fmtKm(q.depth_km)}</td></>, "#ffcc66", quakeLine(q)))}</tbody>
                </table>
              </div>
            </>
          )}
          {!ev.located.length && !ev.events && <p className="ask-note">{ev.count ? "This answer has the day's count but not its hypocentres." : "No mapped instruments in this answer."}</p>}
          {ev.documents.length > 0 && (
            <>
              <div className="ask-label"><span>Further reading</span></div>
              <ul className="ask-reading">
                {ev.documents.map(d => (
                  <li key={d.n} className={live && hl === d.n ? "on" : ""}>
                    <span className="mono">{d.n}</span>
                    {d.url ? <a href={d.url} target="_blank" rel="noreferrer" title={d.quote ? d.excerpt : undefined}>{d.title} ↗</a> : <span>{d.title}</span>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </article>
  );
}
