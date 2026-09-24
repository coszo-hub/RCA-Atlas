import "./ui.css";

export default function RegionNav({ regions, sensors, active, onSelect, unplaced = 0, unplacedOpen = false, onUnplaced }) {
  const located = sensors.filter(s => s.lat != null);
  const items = [["overview", "Full array", located.length],
    ...regions.map(r => [r.key, r.label, located.filter(s => s.region === r.key).length])];
  return (
    <nav className="panel regions" aria-label="Regions">
      <div className="eyebrow" style={{ padding: "6px 10px 4px" }}>Regions</div>
      {items.map(([key, label, n]) => (
        <button key={key} aria-pressed={active === key} onClick={() => onSelect(key)}>
          {label}<span className="n mono">{n}</span>
        </button>
      ))}
      {/* Sensors with no position and no site are not on the map; this is the way to them. */}
      {unplaced > 0 && onUnplaced && (
        <button className="unplaced" aria-pressed={unplacedOpen} onClick={onUnplaced} title="Sensors with no recorded position and no catalogued site">
          Unplaced sensors<span className="n mono">{unplaced}</span>
        </button>
      )}
    </nav>
  );
}
