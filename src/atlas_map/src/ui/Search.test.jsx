import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Search from "./Search.jsx";
import { bundleFixture } from "../test/fixtures.js";

describe("Search", () => {
  const b = bundleFixture();
  it("leaves the box after a pick with Enter, so Escape goes to the panel", () => {
    const onPick = vi.fn();
    render(<Search bundle={b} onPick={onPick} />);
    const box = screen.getByRole("searchbox");
    box.focus();
    fireEvent.change(box, { target: { value: "ctdpfb301" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ kind: "sensor", id: "base-ctd" }));
    expect(box).toHaveValue("");
    expect(document.activeElement).not.toBe(box);
  });
  it("leaves the box after a pick with the mouse", () => {
    const onPick = vi.fn();
    render(<Search bundle={b} onPick={onPick} />);
    const box = screen.getByRole("searchbox");
    box.focus();
    fireEvent.change(box, { target: { value: "mass spec" } });
    const option = screen.getByRole("option", { name: /ASHES PI mass spectrometer/ });
    expect(option).toHaveTextContent("no recorded position");
    fireEvent.mouseDown(option);
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: "pi-massp", located: false }));
    expect(document.activeElement).not.toBe(box);
  });
});
