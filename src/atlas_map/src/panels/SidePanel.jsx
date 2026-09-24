import { useEffect } from "react";
import { MinButton } from "../ui/Minimize.jsx";
import "./panels.css";

// The right-hand panel shell shared by a site and the unplaced-sensor list: a head with a close control, and
// Escape that steps back from a sensor's detail to the list, then closes. Inside a text field Escape belongs
// to that field (the search box clears itself). Minimized (App owns it, since the map reframes), it is a tab at the
// bottom right that restores it; the site stays selected.
export default function SidePanel({ label, eyebrow, title, sub, closeLabel, onClose, onBack, inDetail, minimized = false, onMinimize, children }) {
  useEffect(() => {
    const onKey = e => {
      if (minimized || e.key !== "Escape" || e.target?.closest?.("input, textarea")) return;
      if (inDetail && onBack) onBack(); else onClose();
    };
    addEventListener("keydown", onKey); return () => removeEventListener("keydown", onKey);
  }, [onClose, onBack, inDetail, minimized]);
  if (minimized) {
    return (
      <div className="panel side-tab" role="region" aria-label={label}>
        <button className="restore" aria-expanded="false" title={`Show ${title}`} onClick={() => onMinimize?.(false)}>{title}</button>
        <button className="close" aria-label={closeLabel} onClick={onClose}>×</button>
      </div>
    );
  }
  return (
    <aside className="panel side-panel" aria-label={label}>
      <div className="sp-head">
        <div><div className="eyebrow">{eyebrow}</div>
          <h2>{title}</h2>
          <div className="sub mono">{sub}</div></div>
        <div className="sp-actions">
          {onMinimize && <MinButton label={label} onClick={() => onMinimize(true)} />}
          <button className="close" aria-label={closeLabel} onClick={onClose}>×</button>
        </div>
      </div>
      {children}
    </aside>
  );
}
