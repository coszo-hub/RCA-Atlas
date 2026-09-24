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
