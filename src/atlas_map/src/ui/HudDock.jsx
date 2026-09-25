import { useState } from "react";
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

// The top-right dock: one button each for the terrain controls, the legend and help. Each button toggles its panel,
// which stays open until that button is clicked again; open panels stack under the dock in the buttons' order.
// The terrain controls stay mounted while closed so their switches keep their state; the legend and help are
// stateless and mount only while open (the legend fits its height from where it opens).
export default function HudDock({ scene, deep = false, onDeep, credit, auv = false, subsurface = null }) {
  const [open, setOpen] = useState(() => new Set());
  const toggle = key => setOpen(o => { const n = new Set(o); if (!n.delete(key)) n.add(key); return n; });
  const pop = key => `hud-pop-${key}`;
  return (
    <div className="hud-dock">
      <div className="dock-bar">
        {ITEMS.map(([key, label]) => (
          <button key={key} className="panel dock-btn" aria-label={label} title={label}
            aria-expanded={open.has(key)} aria-controls={key === "terrain" || open.has(key) ? pop(key) : undefined}
            onClick={() => toggle(key)}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" aria-hidden="true">{ICONS[key]}</svg>
          </button>
        ))}
      </div>
      <div className="dock-pops">
        <div id={pop("terrain")} className="dock-pop" role="group" aria-label="Terrain controls" hidden={!open.has("terrain")}>
          <Controls scene={scene} deep={deep} onDeep={onDeep} />
        </div>
        {open.has("legend") && <div id={pop("legend")} className="dock-pop" role="group" aria-label="Legend">
          <Legend credit={credit} auv={auv} subsurface={subsurface} /></div>}
        {open.has("help") && <div id={pop("help")} className="dock-pop" role="group" aria-label="Help"><Help /></div>}
      </div>
    </div>
  );
}
