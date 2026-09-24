import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { chat } from "../api/gateway.js";
import { suggest } from "./suggestions.js";
import "./chat.css";

const KEY = "atlas.chat.open";
export const chatStartsOpen = () => localStorage.getItem(KEY) !== "false";

export default function ChatPanel({ selection, onOpenChange }) {
  const [open, setOpen] = useState(chatStartsOpen);
  const [messages, setMessages] = useState([]), [draft, setDraft] = useState(""), [busy, setBusy] = useState(false);
  const end = useRef(null);
  // Before paint, so the top row starts beside the panel instead of sliding over from the edge on load.
  useLayoutEffect(() => {
    localStorage.setItem(KEY, String(open));
    const root = document.documentElement.style;
    root.setProperty("--left-inset", open ? "412px" : "16px");
    root.setProperty("--strip-reserve", open ? "0px" : "132px");   // the family strip keeps clear of the minimized tab
    onOpenChange?.(open);
  }, [open, onOpenChange]);
  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [messages]);

  const ask = async question => {
    const q = question.trim(); if (q.length < 2 || busy) return;
    setMessages(m => [...m, { role: "user", text: q }]); setDraft(""); setBusy(true);
    const r = await chat(q);
    setBusy(false);
    setMessages(m => [...m, r.ok ? { role: "assistant", text: r.data.answer, citations: r.data.citations }
      : { role: "error", text: `The chat is unavailable right now (${String(r.message ?? "no reason given").trim().replace(/[.\s]+$/, "")}). The map still works.` }]);
  };

  if (!open) return <button className="chat-tab panel" aria-label="Open chat" onClick={() => setOpen(true)}>Ask the Atlas</button>;
  return (
    <aside className="panel chat" aria-label="Atlas chat">
      <div className="chat-head"><span className="eyebrow">Ask the Atlas</span>
        <button aria-label="Minimize chat" onClick={() => setOpen(false)}>–</button></div>
      <div className="chat-log" aria-live="polite">
        {messages.length === 0 && <p className="muted">Questions are answered from the RCA and COSZO corpus, with sources.</p>}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <p>{m.text}</p>
            {m.citations?.length > 0 && <ol className="cites">{m.citations.map((c, j) => <li key={c.id ?? `c${j}`}>{c.url ? <a href={c.url} target="_blank" rel="noreferrer">{c.title}</a> : c.title}</li>)}</ol>}
          </div>
        ))}
        {busy && <p className="muted">Thinking…</p>}
        <div ref={end} />
      </div>
      <div className="chips">{suggest(selection).map(s => <button key={s} onClick={() => ask(s)}>{s}</button>)}</div>
      <form className="chat-input" onSubmit={e => { e.preventDefault(); ask(draft); }}>
        <textarea aria-label="Ask a question" rows="2" value={draft} onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); ask(draft); } }} />
        <button type="submit" disabled={busy}>Send</button>
      </form>
    </aside>
  );
}
