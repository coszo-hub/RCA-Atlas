import { fireEvent, render, screen } from "@testing-library/react";
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
});
