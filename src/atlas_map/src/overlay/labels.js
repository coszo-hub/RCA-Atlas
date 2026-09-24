export function place(items) {
  const boxes = [], shown = new Set();
  for (const it of [...items].sort((a, b) => b.priority - a.priority)) {
    const box = [it.x, it.y - it.h / 2, it.x + it.w, it.y + it.h / 2];
    if (!boxes.some(b => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]))) {
      shown.add(it.id); boxes.push(box);
    }
  }
  return shown;
}

// Region cards sit on a stem above their point. Greedy by priority: a card that would overlap one already
// placed rises by its height plus a gap until it is clear. Returns id -> stem length in px.
export function stems(items, base, gap, maxSteps = 6) {
  const boxes = [], out = new Map();
  for (const it of [...items].sort((a, b) => b.priority - a.priority)) {
    let stem = base, box;
    for (let k = 0; k <= maxSteps; k++, stem += it.h + gap) {
      box = [it.x - it.w / 2, it.y - stem - it.h, it.x + it.w / 2, it.y - stem];
      if (!boxes.some(b => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]))) break;
    }
    boxes.push(box); out.set(it.id, Math.min(stem, base + maxSteps * (it.h + gap)));
  }
  return out;
}
