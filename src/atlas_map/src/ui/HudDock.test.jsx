import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import HudDock from "./HudDock.jsx";

const fakeScene = () => ({ setView: vi.fn(), setStyle: vi.fn(), setColor: vi.fn(), setExag: vi.fn(), U: { exag: { value: 6 } } });
const dock = (scene = fakeScene()) => render(<HudDock scene={scene} credit="GMRT" />);
const btn = name => screen.getByRole("button", { name });

describe("HudDock", () => {
  it("has a Terrain, Legend and Help button, each with a title, all closed to start", () => {
    dock();
    for (const name of ["Terrain controls", "Legend", "Help"]) {
      expect(btn(name)).toHaveAttribute("aria-expanded", "false");
      expect(btn(name)).toHaveAttribute("title");
    }
    expect(screen.queryByRole("button", { name: "Contours" })).toBeNull();   // mounted but hidden
    expect(screen.queryByText("Seafloor depth")).toBeNull();
  });
  it("each button opens its popover", () => {
    dock();
    fireEvent.click(btn("Terrain controls"));
    expect(btn("Terrain controls")).toHaveAttribute("aria-expanded", "true");
    expect(btn("Contours")).toBeVisible();
    fireEvent.click(btn("Legend"));
    expect(screen.getByText("Seafloor depth")).toBeVisible();
    fireEvent.click(btn("Help"));
    expect(screen.getByText(/Drag to move/)).toBeVisible();
    expect(screen.getByText("Ctrl")).toBeVisible();
  });
  it("each popover stays open until its own button is clicked again, and several can be open together", () => {
    dock();
    fireEvent.click(btn("Terrain controls"));
    fireEvent.click(btn("Legend"));
    expect(btn("Terrain controls")).toHaveAttribute("aria-expanded", "true");
    expect(btn("Legend")).toHaveAttribute("aria-expanded", "true");
    expect(btn("Contours")).toBeVisible();
    expect(screen.getByText("Seafloor depth")).toBeVisible();
    fireEvent.click(btn("Legend"));
    expect(btn("Legend")).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Seafloor depth")).toBeNull();
    expect(btn("Contours")).toBeVisible();
  });
  it("Escape and clicks elsewhere leave the popovers open, and Escape still reaches the page", () => {
    const behind = vi.fn();   // e.g. the side panel, which closes on Escape
    addEventListener("keydown", behind);
    try {
      dock();
      fireEvent.click(btn("Terrain controls"));
      fireEvent.click(btn("Legend"));
      fireEvent.keyDown(document.body, { key: "Escape" });
      fireEvent.pointerDown(document.body);
      expect(btn("Terrain controls")).toHaveAttribute("aria-expanded", "true");
      expect(btn("Legend")).toHaveAttribute("aria-expanded", "true");
      expect(behind).toHaveBeenCalledTimes(1);
    } finally { removeEventListener("keydown", behind); }
  });
  it("keeps the terrain settings across closing and reopening", () => {
    const s = fakeScene();
    dock(s);
    fireEvent.click(btn("Terrain controls"));
    fireEvent.click(btn("Contours"));
    fireEvent.click(btn("2D"));
    fireEvent.click(btn("Terrain controls"));
    fireEvent.click(btn("Terrain controls"));
    expect(btn("Contours")).toHaveAttribute("aria-pressed", "true");
    expect(btn("2D")).toHaveAttribute("aria-pressed", "true");
    expect(s.setStyle).toHaveBeenCalledTimes(1);
  });
});
