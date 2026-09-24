import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Legend from "./Legend.jsx";
import { FAMILIES } from "../test/fixtures.js";

describe("Legend", () => {
  it("status samples use a neutral text token, not a family color", () => {
    const { container } = render(<Legend credit="GMRT" />);
    const html = container.innerHTML.toLowerCase();
    for (const c of [...FAMILIES.map(f => f.color), "#d9d6cc"]) expect(html).not.toContain(c.toLowerCase());
    expect(html).toContain("var(--text-secondary)");
  });
});

describe("Legend credits", () => {
  it("credits MBARI for the Axial summit only when its tiles are shown", () => {
    const { rerender } = render(<Legend credit="GMRT" />);
    expect(screen.queryByText(/MBARI/)).toBeNull();
    rerender(<Legend credit="GMRT" auv />);
    expect(screen.getByText(/Axial summit: MBARI AUV survey \(cruise V2506\), 1 m\./)).toBeInTheDocument();
  });
});

describe("Legend subsurface", () => {
  it("explains and credits Axial's subsurface only while it is shown", () => {
    const { rerender } = render(<Legend credit="GMRT" />);
    expect(screen.queryByText("Beneath Axial")).toBeNull();
    rerender(<Legend credit="GMRT" subsurface="Subsurface: M. Kidiwela, axial_visuals" />);
    expect(screen.getByText("Beneath Axial")).toBeInTheDocument();
    expect(screen.getByText("Magma chamber (AMC) top")).toBeInTheDocument();
    expect(screen.getByText(/Subsurface: M\. Kidiwela, axial_visuals\./)).toBeInTheDocument();
  });
});

describe("Legend collapse (layout ruling)", () => {
  it("is expanded when no side panel is open, and the user can collapse it", () => {
    render(<Legend credit="GMRT" compact={false} />);
    expect(screen.getByText("Seafloor depth")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Minimize legend" }));
    expect(screen.queryByText("Seafloor depth")).toBeNull();
    expect(screen.getByRole("button", { name: "Legend" })).toHaveAttribute("aria-expanded", "false");
  });
  it("collapses to a Legend toggle while a panel is open, and the user can expand it", () => {
    render(<Legend credit="GMRT" compact />);
    expect(screen.queryByText("Seafloor depth")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Legend" }));
    expect(screen.getByText("Seafloor depth")).toBeInTheDocument();
  });
  it("follows the panels again when they open or close", () => {
    const { rerender } = render(<Legend credit="GMRT" compact={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Minimize legend" }));
    rerender(<Legend credit="GMRT" compact />);
    rerender(<Legend credit="GMRT" compact={false} />);
    expect(screen.getByText("Seafloor depth")).toBeInTheDocument();
  });
});
