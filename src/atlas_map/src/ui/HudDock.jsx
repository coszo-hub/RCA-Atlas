import { useEffect, useRef, useState } from "react";
import Controls from "./Controls.jsx";
import Legend from "./Legend.jsx";
import "./ui.css";

// 16 px line icons, drawn in currentColor so they follow the button's text color.
const ICONS = {
  terrain: <path d="M1.5 13.5 6 6l2.6 4 1.9-2.6 4 6.1z" />,
  legend: <><rect x="1.8" y="3" width="2.4" height="2.4" /><rect x="1.8" y="10.6" width="2.4" height="2.4" /><path d="M7 4.2h7.2M7 8h7.2M7 11.8h7.2M1.8 8h2.4" /></>,
  help: <><circle cx="8" cy="8" r="6.5" /><path d="M6.1 6.3a1.95 1.95 0 1 1 2.7 1.8c-.5.2-.8.6-.8 1.1v.7" /><circle cx="8" cy="11.6" r=".4" fill="currentColor" /></>,
};
const ITEMS = [["terrain", "Terrain controls"], ["legend", "Legend"], ["help", "Help"]];

function Help() {
  return (
    <div className="panel help">
      <div className="eyebrow">Moving the map</div>
      <div className="hint">Drag to move · <kbd>Ctrl</kbd>-drag to rotate · Scroll to zoom · <kbd>←</kbd><kbd>↑</kbd><kbd>↓</kbd><kbd>→</kbd> to move · Hover the cable or a node for details</div>
    </div>
  );
}

// The top-right dock: one button each for the terrain controls, the legend and help, each opening its panel as a
// popover under the dock. One is open at a time; its button again, Escape, or a click outside the dock closes it.
// The terrain controls stay mounted while closed so their switches keep their state; the legend and help are
// stateless and mount only while open (the legend fits its height from where it opens).
export default function HudDock({ scene, deep = false, onDeep, credit, auv = false, subsurface = null }) {
  const [open, setOpen] = useState(null);
  const ref = useRef(null), buttons = useRef({});
  useEffect(() => {
    if (!open) return;
    const onDown = e => { if (!ref.current?.contains(e.target)) setOpen(null); };
    // Capture, so Escape closes the popover only and does not also reach the side panel behind it.
    const onKey = e => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      setOpen(null); buttons.current[open]?.focus();
    };
    addEventListener("pointerdown", onDown, true); addEventListener("keydown", onKey, true);
    return () => { removeEventListener("pointerdown", onDown, true); removeEventListener("keydown", onKey, true); };
  }, [open]);
  const pop = key => `hud-pop-${key}`;
  return (
    <div className="hud-dock" ref={ref}>
      <div className="dock-bar">
        {ITEMS.map(([key, label]) => (
          <button key={key} ref={el => { buttons.current[key] = el; }} className="panel dock-btn" aria-label={label} title={label}
            aria-expanded={open === key} aria-controls={key === "terrain" || open === key ? pop(key) : undefined}
            onClick={() => setOpen(o => (o === key ? null : key))}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" aria-hidden="true">{ICONS[key]}</svg>
          </button>
        ))}
      </div>
      <div id={pop("terrain")} className="dock-pop" role="group" aria-label="Terrain controls" hidden={open !== "terrain"}>
        <Controls scene={scene} deep={deep} onDeep={onDeep} />
      </div>
      {open === "legend" && <div id={pop("legend")} className="dock-pop" role="group" aria-label="Legend">
        <Legend credit={credit} auv={auv} subsurface={subsurface} /></div>}
      {open === "help" && <div id={pop("help")} className="dock-pop" role="group" aria-label="Help"><Help /></div>}
    </div>
  );
}
