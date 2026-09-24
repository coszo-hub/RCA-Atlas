import { useEffect, useRef, useState } from "react";
import { chat } from "../api/gateway.js";
import { suggest } from "./suggestions.js";
import "./chat.css";

const KEY = "atlas.chat.open";

export default function ChatPanel({ selection }) {
  const [open, setOpen] = useState(() => localStorage.getItem(KEY) !== "false");
  const [messages, setMessages] = useState([]), [draft, setDraft] = useState(""), [busy, setBusy] = useState(false);
  const end = useRef(null);
  useEffect(() => {
    localStorage.setItem(KEY, String(open));
    document.documentElement.style.setProperty("--left-inset", open ? "412px" : "16px");
  }, [open]);
  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [messages]);

  const ask = async question => {
    const q = question.trim(); if (q.length < 2 || busy) return;
    setMessages(m => [...m, { role: "user", text: q }]); setDraft(""); setBusy(true);
    const r = await chat(q);
    setBusy(false);
    setMessages(m => [...m, r.ok ? { role: "assistant", text: r.data.answer, citations: r.data.citations }
      : { role: "error", text: `The chat is unavailable right now (${r.message}). The map still works.` }]);
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
            {m.citations?.length > 0 && <ol className="cites">{m.citations.map(c => <li key={c.id}>{c.url ? <a href={c.url} target="_blank" rel="noreferrer">{c.title}</a> : c.title}</li>)}</ol>}
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
