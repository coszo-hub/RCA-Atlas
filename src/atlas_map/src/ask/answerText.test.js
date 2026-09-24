import { describe, expect, it } from "vitest";
import { parseAnswer } from "./answerText.js";

const known = new Set([1, 2, 3, 4]);

describe("parseAnswer", () => {
  it("turns [n] and [n, m] markers into citations, dropping the space before them", () => {
    const [p] = parseAnswer("Tilt is tracked in the caldera [1][2], and seismicity [3, 4] climbs.", known);
    expect(p).toEqual({ type: "p", parts: [
      { t: "text", v: "Tilt is tracked in the caldera" }, { t: "cite", n: 1 }, { t: "cite", n: 2 },
      { t: "text", v: ", and seismicity" }, { t: "cite", n: 3 }, { t: "cite", n: 4 }, { t: "text", v: " climbs." }] });
  });
  it("ranges expand; unknown numbers stay plain text", () => {
    const [p] = parseAnswer("See [2–4] and [9].", known);
    expect(p.parts).toEqual([{ t: "text", v: "See" }, { t: "cite", n: 2 }, { t: "cite", n: 3 }, { t: "cite", n: 4 }, { t: "text", v: " and [9]." }]);
  });
  it("paragraphs, bullets (nested), section labels and bold", () => {
    const blocks = parseAnswer("A direct answer.\n\nInstruments and Measurements\n- Bottom pressure [1]\n    - Identity: continuous\n**Seismic record**\nMore **text** here.\n---\nEnd.", known);
    expect(blocks.map(b => [b.type, b.level ?? 0])).toEqual([["p", 0], ["h", 0], ["li", 0], ["li", 1], ["h", 0], ["p", 0], ["p", 0]]);
    expect(blocks[1].parts).toEqual([{ t: "text", v: "Instruments and Measurements" }]);
    expect(blocks[5].parts).toEqual([{ t: "text", v: "More " }, { t: "b", v: "text" }, { t: "text", v: " here." }]);
  });
  it("text without markers is one plain paragraph per block", () => {
    expect(parseAnswer("There were 71 Axial Seamount earthquakes.", known)).toEqual([{ type: "p", parts: [{ t: "text", v: "There were 71 Axial Seamount earthquakes." }] }]);
    expect(parseAnswer("", known)).toEqual([]);
  });
});
