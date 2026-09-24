import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Controls from "./Controls.jsx";

const fakeScene = () => ({ setView: vi.fn(), setStyle: vi.fn(), setColor: vi.fn(), setExag: vi.fn(), U: { exag: { value: 6 } } });

describe("Controls", () => {
  it("switches are independent", () => {
    const s = fakeScene();
    render(<Controls scene={s} />);
    fireEvent.click(screen.getByRole("button", { name: "Contours" }));
    fireEvent.click(screen.getByRole("button", { name: "2D" }));
    fireEvent.click(screen.getByRole("button", { name: "Mono" }));
    expect(s.setStyle).toHaveBeenCalledWith("contours");
    expect(s.setView).toHaveBeenCalledWith("2d");
    expect(s.setColor).toHaveBeenCalledWith("mono");
    expect(screen.getByRole("button", { name: "Contours" })).toHaveAttribute("aria-pressed", "true");
  });
  it("disables exaggeration in 2D", () => {
    render(<Controls scene={fakeScene()} />);
    const slider = screen.getByRole("slider", { name: /vertical/i });
    expect(slider).not.toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "2D" }));
    expect(slider).toBeDisabled();
  });
  it("shows the navigation hint", () => {
    render(<Controls scene={fakeScene()} />);
    expect(screen.getByText(/Ctrl/)).toBeInTheDocument();
    expect(screen.getByText(/Drag to move/)).toBeInTheDocument();
  });
  it("reads out the finest Axial summit level on screen", () => {
    vi.useFakeTimers();
    try {
      let finest = "16 m";
      render(<Controls scene={{ ...fakeScene(), auv: { finest: () => finest } }} />);
      expect(screen.getByText("Axial detail")).toBeInTheDocument();
      expect(screen.getByText("16 m")).toBeInTheDocument();
      finest = "1 m";
      act(() => { vi.advanceTimersByTime(300); });
      expect(screen.getByText("1 m")).toBeInTheDocument();
    } finally { vi.useRealTimers(); }
  });
  it("has no Axial detail row when the AUV tiles are not built", () => {
    render(<Controls scene={fakeScene()} />);
    expect(screen.queryByText("Axial detail")).toBeNull();
  });
  it("collapses to a toggle while the top row wraps, keeps its switches, and the user can expand and collapse it", () => {
    const s = fakeScene();
    const { rerender } = render(<Controls scene={s} />);
    fireEvent.click(screen.getByRole("button", { name: "Contours" }));
    rerender(<Controls scene={s} compact />);
    expect(screen.queryByRole("button", { name: "Contours" })).toBeNull();
    const toggle = screen.getByRole("button", { name: "Terrain controls" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Contours" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Collapse terrain controls" }));
    expect(screen.getByRole("button", { name: "Terrain controls" })).toBeInTheDocument();
    rerender(<Controls scene={s} compact={false} />);
    expect(screen.getByRole("button", { name: "Contours" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Collapse terrain controls" })).toBeNull();
  });
  it("has no Subsurface switch when the subsurface layer is not built", () => {
    render(<Controls scene={fakeScene()} />);
    expect(screen.queryByRole("group", { name: "Subsurface" })).toBeNull();
  });
  it("switches Axial's subsurface on, then scrubs and plays the earthquakes month by month", () => {
    vi.useFakeTimers();
    try {
      const sub = { months: [{ label: "2015-01", end: 10 }, { label: "2015-02", end: 38 }, { label: "2015-03", end: 69 }],
                    countThrough: i => [120, 4500, 12000][i] };
      const s = { ...fakeScene(), subsurface: sub, setSubsurface: vi.fn(), setQuakesThrough: vi.fn() };
      const onDeep = vi.fn();
      const { rerender } = render(<Controls scene={s} onDeep={onDeep} />);
      expect(screen.queryByRole("slider", { name: /earthquakes/i })).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "On" }));
      expect(onDeep).toHaveBeenCalledWith(true);
      expect(s.setSubsurface).toHaveBeenCalledWith(true);
      rerender(<Controls scene={s} deep onDeep={onDeep} />);
      expect(screen.getByText("to 2015-03 · 12,000")).toBeInTheDocument();   // the whole catalog to start
      fireEvent.change(screen.getByRole("slider", { name: /earthquakes/i }), { target: { value: "0" } });
      expect(s.setQuakesThrough).toHaveBeenLastCalledWith(0);
      expect(screen.getByText("to 2015-01 · 120")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Play month by month" }));
      act(() => { vi.advanceTimersByTime(300); });
      expect(s.setQuakesThrough).toHaveBeenLastCalledWith(2);
      expect(screen.getByRole("button", { name: "Play month by month" })).toBeInTheDocument();   // stops at the end
    } finally { vi.useRealTimers(); }
  });
});
