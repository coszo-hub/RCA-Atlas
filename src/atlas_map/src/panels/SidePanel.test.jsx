import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import SidePanel from "./SidePanel.jsx";
import { chartHeight } from "./live/Chart.jsx";
import { SIDE_DEFAULT, SIDE_MIN, clampSide, setSideWidth, sideMax } from "../ui/sideWidth.js";

const panel = () => render(<SidePanel label="Site" eyebrow="Site" title="Axial Base" sub="" closeLabel="Close" onClose={() => {}}>body</SidePanel>);
const width = () => parseFloat(screen.getByRole("complementary", { name: "Site" }).style.width);
let savedWidth;
beforeEach(() => { savedWidth = window.innerWidth; window.innerWidth = 1600; });
afterEach(() => { act(() => setSideWidth(SIDE_DEFAULT)); window.innerWidth = savedWidth; });

describe("side panel width", () => {
  it("is limited to a minimum and to what leaves the chat and some map beside it", () => {
    expect(clampSide(100, 1600)).toBe(SIDE_MIN);
    expect(sideMax(1600, 412)).toBe(812);   // beside the open chat
    expect(sideMax(1600, 16)).toBe(1208);   // the chat minimized gives its room to the panel
    expect(clampSide(5000, 1600, 412)).toBe(812);
    expect(sideMax(1024, 412)).toBe(SIDE_DEFAULT);   // a small window keeps the panel it always had
  });

  it("drags wider from its left edge and resets on double-click", () => {
    panel();
    const edge = screen.getByRole("separator", { name: "Resize panel" });
    expect(width()).toBe(SIDE_DEFAULT);
    edge.setPointerCapture = () => {};
    fireEvent.pointerDown(edge, { button: 0, clientX: 1000, pointerId: 1 });
    fireEvent.pointerMove(edge, { clientX: 880, pointerId: 1 });   // 120 px to the left
    fireEvent.pointerUp(edge, { pointerId: 1 });
    expect(width()).toBe(SIDE_DEFAULT + 120);
    fireEvent.pointerMove(edge, { clientX: 500, pointerId: 1 });   // after release the pointer no longer resizes
    expect(width()).toBe(SIDE_DEFAULT + 120);
    fireEvent.doubleClick(edge);
    expect(width()).toBe(SIDE_DEFAULT);
  });

  it("resizes from the keyboard: ← widens, → narrows, Home restores", () => {
    panel();
    const edge = screen.getByRole("separator", { name: "Resize panel" });
    fireEvent.keyDown(edge, { key: "ArrowLeft" });
    expect(width()).toBe(SIDE_DEFAULT + 24);
    fireEvent.keyDown(edge, { key: "ArrowRight", shiftKey: true });
    expect(width()).toBe(SIDE_DEFAULT + 24 - 96);
    fireEvent.keyDown(edge, { key: "Home" });
    expect(width()).toBe(SIDE_DEFAULT);
    expect(edge).toHaveAttribute("aria-valuenow", String(SIDE_DEFAULT));
  });

  it("charts keep 200 px at the default width and grow taller as the panel widens", () => {
    expect(chartHeight(SIDE_DEFAULT - 32)).toBe(200);
    expect(chartHeight(700)).toBe(336);
    expect(chartHeight(2000)).toBe(420);
  });
});
