import { useEffect, useRef } from "react";
import { MinButton } from "../ui/Minimize.jsx";
import { SIDE_DEFAULT, SIDE_MIN, clampSide, setSideWidth, sideMax, useSideWidth } from "../ui/sideWidth.js";
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
  const width = useSideWidth();
  if (minimized) {
    return (
      <div className="panel side-tab" role="region" aria-label={label}>
        <button className="restore" aria-expanded="false" title={`Show ${title}`} onClick={() => onMinimize?.(false)}>{title}</button>
        <button className="close" aria-label={closeLabel} onClick={onClose}>×</button>
      </div>
    );
  }
  return (
    <>
      <ResizeEdge width={width} />
      <aside className="panel side-panel" aria-label={label} style={{ width }}>
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
    </>
  );
}

// The panel's left edge: drag it (or focus it and use ← / →) to widen the panel for its charts and plots, and
// double-click to restore the default width. The panel sits 16 px from the window's right edge.
function ResizeEdge({ width }) {
  const drag = useRef(null);
  const onPointerDown = e => {
    if (e.button !== 0) return;
    e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, w: width };
    document.body.classList.add("resizing-side");
  };
  const onPointerMove = e => { if (drag.current) setSideWidth(drag.current.w + drag.current.x - e.clientX); };
  const end = () => { drag.current = null; document.body.classList.remove("resizing-side"); };
  const onKeyDown = e => {
    const step = e.shiftKey ? 96 : 24;
    if (e.key === "ArrowLeft") { e.preventDefault(); setSideWidth(width + step); }
    else if (e.key === "ArrowRight") { e.preventDefault(); setSideWidth(width - step); }
    else if (e.key === "Home") { e.preventDefault(); setSideWidth(SIDE_DEFAULT); }
  };
  return (
    <div className="sp-resize" style={{ right: 16 + width - 5 }} role="separator" aria-orientation="vertical" aria-label="Resize panel" tabIndex={0}
      aria-valuemin={SIDE_MIN} aria-valuemax={sideMax()} aria-valuenow={clampSide(width)} title="Drag to resize · double-click to reset"
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={end} onPointerCancel={end}
      onDoubleClick={() => setSideWidth(SIDE_DEFAULT)} onKeyDown={onKeyDown} />
  );
}
