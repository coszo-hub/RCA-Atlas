import { useSyncExternalStore } from "react";

// The right-hand panel's width, which its left edge drags. App reads it to reframe the map and the HUD; the
// panel sets it. The viewer's last width is remembered (a convenience, so storage failing changes nothing).
export const SIDE_DEFAULT = 440, SIDE_MIN = 360;
const STORE_KEY = "atlas.sideWidth";
const MAP_KEEP = 360;   // map left beside the panel at its widest: room for the top row's header card
let leftInset = 412;    // what the left side takes (the chat when open, else its 16 px margin); App keeps it current

// The widest the panel may be in this window: the chat (if open) and some map stay beside it. Never below the
// default, so a small window keeps the panel it always had.
export const sideMax = (viewport = innerWidth, left = leftInset) => Math.max(SIDE_DEFAULT, Math.min(1400, viewport - left - 16 - MAP_KEEP));
export const clampSide = (w, viewport = innerWidth, left = leftInset) => Math.round(Math.min(sideMax(viewport, left), Math.max(SIDE_MIN, w)));

let width = (() => {
  try { const v = Number(localStorage.getItem(STORE_KEY)); return v >= SIDE_MIN ? v : SIDE_DEFAULT; } catch { return SIDE_DEFAULT; }
})();
const listeners = new Set();

export function setSideWidth(w) {
  const next = clampSide(w);
  if (next === width) return;
  width = next;
  try { localStorage.setItem(STORE_KEY, String(width)); } catch { /* private mode: not remembered */ }
  for (const l of listeners) l();
}

// Opening the chat takes room on the left, so a wide panel narrows to fit; closing it gives the room back.
export function setSideRoom(left) {
  if (left === leftInset) return;
  leftInset = left;
  for (const l of listeners) l();
}

// A narrower window can make the saved width too wide; readers get it clamped to the current window.
if (typeof addEventListener === "function") addEventListener("resize", () => { for (const l of listeners) l(); });
const subscribe = l => { listeners.add(l); return () => listeners.delete(l); };
export const useSideWidth = () => useSyncExternalStore(subscribe, () => clampSide(width));
