import { toX, toZ } from "./geo.js";

export const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export function viewPose(view, elevAt) {
  const [lon, lat] = view.ll;
  const target = [toX(lon), elevAt(lon, lat) * 0.001 * view.exag, toZ(lat)];
  const s = Math.sin(view.polar), c = Math.cos(view.polar);
  // matches THREE.Vector3.setFromSphericalCoords(r, phi, theta)
  const off = [view.dist * s * Math.sin(view.az), view.dist * c, view.dist * s * Math.cos(view.az)];
  return { pos: [target[0] + off[0], target[1] + off[1], target[2] + off[2]], target };
}

export function moveStep(held, cam, target, dt) {
  let fx = target[0] - cam[0], fz = target[2] - cam[2];
  const fl = Math.hypot(fx, fz) || 1; fx /= fl; fz /= fl;
  const rx = -fz, rz = fx;   // right = forward × up
  let x = 0, z = 0;
  if (held.has("ArrowUp")) { x += fx; z += fz; }
  if (held.has("ArrowDown")) { x -= fx; z -= fz; }
  if (held.has("ArrowRight")) { x += rx; z += rz; }
  if (held.has("ArrowLeft")) { x -= rx; z -= rz; }
  const len = Math.hypot(x, z);
  if (!len) return [0, 0, 0];
  const dist = Math.hypot(cam[0] - target[0], cam[1] - target[1], cam[2] - target[2]);
  const k = (0.3 * dist * dt) / len;
  return [x * k, 0, z * k];
}

export const isTypingTarget = el =>
  !!el && (el.isContentEditable || el.contentEditable === "true" || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));

// Rotation slows as the camera closes in (a drag swings the whole view, which is too much up close):
// full speed from 30 km out, the square root of the distance below that, never under a fifth.
export const rotateSpeedFor = dist => Math.min(1, Math.max(0.2, Math.sqrt(dist / 30)));

// prefers-reduced-motion: flights jump to their end and uniform transitions snap.
export const motionDuration = (ms, reduced) => (reduced ? 0 : ms);
export const approach = (value, target, dt, speed, reduced) =>
  reduced ? target : value + (target - value) * Math.min(1, dt * speed);

// Focus inside a panel (site panel, chat, HUD) keeps the arrows there, so a panel scrolls instead of the map moving.
export const inPanel = el => !!el?.closest?.(".panel, aside");

// macOS sends no keyup for other keys while Cmd is held, so modified arrows never start a move.
export const isMoveKey = e =>
  !!e.key?.startsWith("Arrow") && !(e.metaKey || e.ctrlKey || e.altKey) && !isTypingTarget(e.target) && !inPanel(e.target);

// Side panels cover the map's edges. The view's center moves to the middle of the free area between
// them (pixels to shift right), and a view framed for the full width pulls back to fit the free width.
export const centerShift = (left, right) => (left - right) / 2;
export const fitDist = (dist, width, left, right) =>
  dist * Math.max(1, (width - 32) / Math.max(320, width - left - right));
