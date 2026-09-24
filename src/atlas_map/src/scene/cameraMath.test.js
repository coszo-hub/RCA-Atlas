import { describe, expect, it } from "vitest";
import { approach, centerShift, ease, fitDist, isMoveKey, isTypingTarget, motionDuration, moveStep, viewPose } from "./cameraMath.js";

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
  it("reduced motion makes flights instant and snaps uniform easing", () => {
    expect(motionDuration(1800, false)).toBe(1800);
    expect(motionDuration(1800, true)).toBe(0);
    expect(approach(0, 1, 0.016, 5, false)).toBeCloseTo(0.08);
    expect(approach(0, 1, 0.016, 5, true)).toBe(1);
    expect(approach(0, 1, 1, 5, false)).toBe(1);
  });
  it("arrow keys move only without Cmd/Ctrl/Alt and outside form fields", () => {
    const div = document.createElement("div"), input = document.createElement("input");
    expect(isMoveKey({ key: "ArrowUp", target: div })).toBe(true);
    expect(isMoveKey({ key: "a", target: div })).toBe(false);
    expect(isMoveKey({ key: "ArrowUp", target: input })).toBe(false);
    for (const mod of ["metaKey", "ctrlKey", "altKey"]) expect(isMoveKey({ key: "ArrowLeft", target: div, [mod]: true })).toBe(false);
  });
  it("a keydown without a key (Chrome autofill) is not a move key", () => {
    expect(isMoveKey({ key: undefined, target: document.createElement("div") })).toBe(false);
    expect(isMoveKey({ target: document.createElement("div") })).toBe(false);
  });
});

describe("framing between the side panels", () => {
  it("shifts the view center to the middle of the free area", () => {
    expect(centerShift(412, 16)).toBe(198);
    expect(centerShift(16, 472)).toBe(-228);
    expect(centerShift(16, 16)).toBe(0);
  });
  it("pulls a view back so what fit the full width fits the free width", () => {
    expect(fitDist(100, 1600, 16, 16)).toBe(100);
    expect(fitDist(100, 1600, 412, 16)).toBeCloseTo(100 * 1568 / 1172, 6);
    expect(fitDist(100, 1600, 0, 0)).toBe(100);   // never closer than the designed view
    expect(fitDist(100, 500, 412, 472)).toBeCloseTo(100 * 468 / 320, 6);   // free width floors at 320 px
  });
});
