// March the sight line from the camera to the point over the heightfield; stop just short of the point.
export function occluded(cam, point, groundY, steps = 48) {
  for (let i = 1; i < steps; i++) {
    const k = i / steps;
    if (k > 0.97) break;
    const x = cam[0] + (point[0] - cam[0]) * k, y = cam[1] + (point[1] - cam[1]) * k, z = cam[2] + (point[2] - cam[2]) * k;
    if (y < groundY(x, z) - 0.02) return true;
  }
  return false;
}
