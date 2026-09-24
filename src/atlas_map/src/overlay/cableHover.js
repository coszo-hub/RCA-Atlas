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

// Projected points behind the camera (z > 1) are dropped; the runs on either side stay separate lines.
export function frontRuns(proj) {
  const runs = [];
  let run = [];
  for (const p of proj) {
    if (p[2] < 1) run.push(p);
    else { if (run.length > 1) runs.push(run); run = []; }
  }
  if (run.length > 1) runs.push(run);
  return runs;
}
