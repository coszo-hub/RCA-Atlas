export function nearest(px, py, lines, maxPx = 7) {
  let best = null, bd = maxPx;
  for (const { info, pts } of lines) for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1], dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy || 1;
    const k = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L));
    const d = Math.hypot(px - ax - k * dx, py - ay - k * dy);
    if (d < bd) { bd = d; best = info; }
  }
  return best;
}
