// The answer's plain text as blocks for rendering: paragraphs, bullets (nested by indent), section labels, and fenced
// code (a download recipe's script, ```python ... ```, kept line for line), with inline **bold** and [n] citations (a
// run like [1-15] is one { n, to }). Numbers the evidence does not know stay as plain text.

const LIST = /^(\s*)[-*•]\s+(.*)$/;
// Ranges take any hyphen: Groq's GPT-OSS writes [1‑6] with U+2011, a non-breaking hyphen.
const CITE = /\s*\[(\d+(?:\s*[,–\u2010-\u2012-]\s*\d+)*)\]/g;

// A marker's citations: single numbers, and ranges ([1-15]) as one { n, to } when they span three or more.
function cites(group) {
  return group.split(/\s*,\s*/).flatMap(part => {
    const [a, b] = part.split(/\s*[–\u2010-\u2012-]\s*/).map(Number);
    if (!(b > a && b - a < 50)) return [{ n: a }];
    return b - a >= 2 ? [{ n: a, to: b }] : [{ n: a }, { n: b }];
  });
}
const numsOf = c => (c.to ? Array.from({ length: c.to - c.n + 1 }, (_, i) => c.n + i) : [c.n]);

function inline(text, known) {
  const parts = [];
  const push = (t, v) => { if (!v) return; const last = parts[parts.length - 1]; if (t === "text" && last?.t === "text") last.v += v; else parts.push({ t, v }); };
  const bolds = text.split(/\*\*(.+?)\*\*/);
  bolds.forEach((chunk, i) => {
    if (i % 2) return push("b", chunk);
    let at = 0;
    for (const m of chunk.matchAll(CITE)) {
      const cs = cites(m[1]);
      push("text", chunk.slice(at, m.index));
      if (cs.flatMap(numsOf).every(n => known.has(n))) for (const c of cs) parts.push({ t: "cite", ...c });
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
  let code = null;   // the open fenced block: { lang, lines }
  lines.forEach((raw, i) => {
    const fence = /^\s*```\s*([\w+-]*)\s*$/.exec(raw);
    if (code) {
      if (fence) { blocks.push({ type: "code", lang: code.lang, text: code.lines.join("\n") }); code = null; }
      else code.lines.push(raw);
      return;
    }
    if (fence) { close(); indents = []; code = { lang: fence[1] || "", lines: [] }; return; }
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
  if (code) blocks.push({ type: "code", lang: code.lang, text: code.lines.join("\n") });   // an unclosed fence runs to the end
  return blocks;
}
