// The answer's plain text as blocks for rendering: paragraphs, bullets (nested by indent), and section labels,
// with inline **bold** and [n] citations. Numbers the evidence does not know stay as plain text.

const LIST = /^(\s*)[-*•]\s+(.*)$/;
const CITE = /\s*\[(\d+(?:\s*[,–-]\s*\d+)*)\]/g;

function nums(group) {
  return group.split(/\s*,\s*/).flatMap(part => {
    const [a, b] = part.split(/\s*[–-]\s*/).map(Number);
    return b && b >= a && b - a < 50 ? Array.from({ length: b - a + 1 }, (_, i) => a + i) : [a];
  });
}

function inline(text, known) {
  const parts = [];
  const push = (t, v) => { if (!v) return; const last = parts[parts.length - 1]; if (t === "text" && last?.t === "text") last.v += v; else parts.push({ t, v }); };
  const bolds = text.split(/\*\*(.+?)\*\*/);
  bolds.forEach((chunk, i) => {
    if (i % 2) return push("b", chunk);
    let at = 0;
    for (const m of chunk.matchAll(CITE)) {
      const ns = nums(m[1]);
      push("text", chunk.slice(at, m.index));
      if (ns.every(n => known.has(n))) for (const n of ns) parts.push({ t: "cite", n });
      else push("text", m[0]);
      at = m.index + m[0].length;
    }
    push("text", chunk.slice(at));
  });
  return parts;
}

export function parseAnswer(text, known = new Set()) {
  const lines = String(text ?? "").split(/\r?\n/), blocks = [];
  let para = null, indents = [];   // the open list's indents, so nesting follows the text's own step (2 or 4 spaces)
  const close = () => { if (para) blocks.push({ type: "p", parts: inline(para.join(" "), known) }); para = null; };
  const levelOf = w => {
    while (indents.length && indents[indents.length - 1] > w) indents.pop();
    if (!indents.length || indents[indents.length - 1] < w) indents.push(w);
    return Math.min(2, indents.length - 1);
  };
  const nextLine = i => lines.slice(i + 1).find(l => l.trim());
  lines.forEach((raw, i) => {
    const line = raw.trim();
    if (!line || /^-{3,}$/.test(line)) { indents = []; return close(); }
    const li = LIST.exec(raw);
    if (li) { close(); blocks.push({ type: "li", level: levelOf(li[1].replace(/\t/g, "    ").length), parts: inline(li[2].trim(), known) }); return; }
    const bold = /^\*\*([^*]+)\*\*:?$/.exec(line);
    const label = bold || (line.length <= 60 && !/[.?!;,]$/.test(line) && LIST.test(nextLine(i) ?? ""));
    indents = [];
    if (label) { close(); blocks.push({ type: "h", parts: inline((bold ? bold[1] : line).replace(/:$/, ""), known) }); return; }
    (para ??= []).push(line);
  });
  close();
  return blocks;
}
