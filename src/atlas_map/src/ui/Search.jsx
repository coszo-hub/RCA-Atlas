import { useMemo, useRef, useState } from "react";
import { searchAtlas } from "../data/search.js";

export default function Search({ bundle, onPick }) {
  const [q, setQ] = useState(""), [active, setActive] = useState(0);
  const results = useMemo(() => searchAtlas(bundle, q), [bundle, q]);
  const input = useRef(null);
  // Leave the box after a pick, so Escape reaches the panel that opened (inside a text field it only clears the field).
  const pick = r => { onPick(r); setQ(""); input.current?.blur(); };
  return (
    <div className="search">
      <input ref={input} type="search" placeholder="Search sensors and sites" value={q} aria-label="Search sensors and sites"
        onChange={e => { setQ(e.target.value); setActive(0); }}
        onKeyDown={e => {
          if (e.key === "ArrowDown") { e.preventDefault(); setActive(a => Math.min(a + 1, results.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
          if (e.key === "Enter" && results[active]) pick(results[active]);
          if (e.key === "Escape") setQ("");
        }} />
      {results.length > 0 && (
        <ul role="listbox">
          {results.map((r, i) => (
            <li key={`${r.kind}-${r.id}`} role="option" aria-selected={i === active} className={r.located === false ? "unlocated" : undefined}
              onMouseDown={e => { e.preventDefault(); pick(r); }}>
              <span>{r.title}</span><span className="sub">{r.sub}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
