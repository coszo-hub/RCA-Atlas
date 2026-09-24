import { useEffect, useState } from "react";
import "./ui.css";

// Every panel can be minimized to a one-line tab and restored from it. Panels the layout does not collapse on its own
// remember the reader's choice across visits, like the chat does.
export function useMinimized(key, initial = false) {
  const storeKey = `atlas.min.${key}`;
  const [min, setMin] = useState(() => {
    const saved = localStorage.getItem(storeKey);
    return saved == null ? initial : saved === "true";
  });
  useEffect(() => { localStorage.setItem(storeKey, String(min)); }, [storeKey, min]);
  return [min, setMin];
}

// The "–" in a panel's head. `label` names the panel for screen readers ("Minimize legend").
export function MinButton({ label, onClick }) {
  return <button className="min-btn" aria-label={`Minimize ${label}`} aria-expanded="true" onClick={onClick}>–</button>;
}

// The minimized panel: its name on a small tab; clicking it restores the panel.
export function MinTab({ children, className = "", onClick, title }) {
  return <button className={`panel hud-toggle ${className}`} aria-expanded="false" title={title} onClick={onClick}>{children}</button>;
}
