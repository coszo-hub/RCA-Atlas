import { MinButton, MinTab, useMinimized } from "./Minimize.jsx";
import Search from "./Search.jsx";
import "./ui.css";

export default function Header({ bundle, onPick }) {
  const located = bundle.sensors.filter(s => s.lat != null);
  const operating = located.filter(s => s.statusGroup === "operating").length;
  const [min, setMin] = useMinimized("header");
  if (min) return <MinTab className="header-toggle" title="Show the title, counts, and search" onClick={() => setMin(false)}>Cascadia Offshore Sensor Atlas</MinTab>;
  return (
    <header className="panel header">
      <div className="panel-head"><h1>Cascadia Offshore Sensor Atlas</h1><MinButton label="title and search" onClick={() => setMin(true)} /></div>
      <p>OOI Regional Cabled Array and COSZO sensors, offshore Oregon.</p>
      <div className="stats">
        <div><b className="mono">{located.length}</b><span>Sensors</span></div>
        <div><b className="mono">{operating}</b><span>Operating</span></div>
        <div><b className="mono">{bundle.sites.length}</b><span>Sites</span></div>
      </div>
      <Search bundle={bundle} onPick={onPick} />
    </header>
  );
}
