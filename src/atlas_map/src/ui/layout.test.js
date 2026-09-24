import { describe, expect, it } from "vitest";
import { hudBottom } from "./layout.js";

const box = bottom => { const d = document.createElement("div"); d.getBoundingClientRect = () => ({ bottom }); return d; };

describe("top-row layout", () => {
  it("the HUD's lowest edge is the lower of the left stack and the dock", () => {
    expect(hudBottom(box(360), box(46))).toBe(360);
    expect(hudBottom(box(40), box(46))).toBe(46);   // header and regions minimized to tabs
    expect(hudBottom(box(360), null)).toBe(360);
    expect(hudBottom(null, null)).toBe(0);
  });
});
