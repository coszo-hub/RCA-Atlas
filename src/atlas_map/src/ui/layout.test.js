import { describe, expect, it } from "vitest";
import { hudBottom, hudWraps } from "./layout.js";

const box = (bottom, cls = "") => { const d = document.createElement("div"); d.className = cls; d.getBoundingClientRect = () => ({ bottom }); return d; };

describe("top-row layout", () => {
  it("wraps when the map between the panels is narrower than header plus controls", () => {
    expect(hudWraps(1600, true, true)).toBe(false);    // 716 px free
    expect(hudWraps(1600, true, false)).toBe(false);
    expect(hudWraps(1366, true, true)).toBe(true);     // 482 px
    expect(hudWraps(1280, true, true)).toBe(true);     // 396 px
    expect(hudWraps(1280, true, false)).toBe(false);   // chat alone: 852 px
    expect(hudWraps(1068, false, true)).toBe(false);   // exactly 580 px fits
    expect(hudWraps(1067, false, true)).toBe(true);
  });
  it("the HUD's lowest edge counts the right stack's controls and toggles, not an expanded legend", () => {
    const left = box(360), right = document.createElement("div");
    right.append(box(220, "panel controls"), box(640, "panel legend"));
    expect(hudBottom(left, right)).toBe(360);
    const wrapped = document.createElement("div");
    wrapped.append(box(410, "panel hud-toggle controls-toggle"), box(410, "panel hud-toggle legend-toggle"));
    expect(hudBottom(left, wrapped)).toBe(410);
    expect(hudBottom(left, null)).toBe(360);
  });
});
