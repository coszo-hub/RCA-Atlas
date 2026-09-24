import { useEffect } from "react";
import "./panels.css";

// The right-hand panel shell shared by a site and the unplaced-sensor list: a head with a close control, and
// Escape that steps back from a sensor's detail to the list, then closes. Inside a text field Escape belongs
// to that field (the search box clears itself).
export default function SidePanel({ label, eyebrow, title, sub, closeLabel, onClose, onBack, inDetail, children }) {
  useEffect(() => {
    const onKey = e => {
      if (e.key !== "Escape" || e.target?.closest?.("input, textarea")) return;
      if (inDetail && onBack) onBack(); else onClose();
    };
    addEventListener("keydown", onKey); return () => removeEventListener("keydown", onKey);
  }, [onClose, onBack, inDetail]);
  return (
    <aside className="panel side-panel" aria-label={label}>
      <div className="sp-head">
        <div><div className="eyebrow">{eyebrow}</div>
          <h2>{title}</h2>
          <div className="sub mono">{sub}</div></div>
        <button className="close" aria-label={closeLabel} onClick={onClose}>×</button>
      </div>
      {children}
    </aside>
  );
}
