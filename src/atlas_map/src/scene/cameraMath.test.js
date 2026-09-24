import { describe, expect, it } from "vitest";
import { ease, isTypingTarget, moveStep, viewPose } from "./cameraMath.js";

describe("cameraMath", () => {
  it("viewPose puts the target on the exaggerated seafloor", () => {
    const p = viewPose({ ll: [-127.15, 45.15], dist: 10, polar: 0, az: 0, exag: 3 }, () => -2000);
    expect(p.target[1]).toBeCloseTo(-6);
    expect(p.pos[1]).toBeCloseTo(4);
  });
  it("arrow keys move forward along the ground at 0.3 × distance per second", () => {
    const d = moveStep(new Set(["ArrowUp"]), [0, 10, 10], [0, 0, 0], 1);
    expect(d[0]).toBeCloseTo(0);
    expect(d[1]).toBe(0);
    expect(d[2]).toBeCloseTo(-0.3 * Math.hypot(10, 10));
  });
  it("opposite keys cancel", () => {
    expect(moveStep(new Set(["ArrowLeft", "ArrowRight"]), [0, 10, 10], [0, 0, 0], 1)).toEqual([0, 0, 0]);
  });
  it("typing targets", () => {
    const input = document.createElement("input");
    const div = document.createElement("div");
    const editable = document.createElement("div");
    editable.contentEditable = "true";
    expect(isTypingTarget(input)).toBe(true);
    expect(isTypingTarget(div)).toBe(false);
    expect(isTypingTarget(editable)).toBe(true);
  });
  it("ease", () => {
    expect(ease(0)).toBe(0);
    expect(ease(1)).toBe(1);
    expect(ease(0.5)).toBeCloseTo(0.5);
  });
});
