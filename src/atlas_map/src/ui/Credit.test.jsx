import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Credit from "./Credit.jsx";

describe("Credit", () => {
  it("names GMRT with its licence, and MBARI when the Axial summit tiles are shown", () => {
    const { rerender } = render(<Credit credit="GMRT, Ryan et al. (2009), CC BY 4.0" />);
    const line = screen.getByLabelText("Map credits");
    expect(line).toHaveTextContent("Bathymetry: GMRT, Ryan et al. (2009), CC BY 4.0");
    expect(line).not.toHaveTextContent("MBARI");
    rerender(<Credit credit="GMRT, Ryan et al. (2009), CC BY 4.0" auv />);
    expect(line).toHaveTextContent("Bathymetry: GMRT, Ryan et al. (2009), CC BY 4.0 · Axial summit: MBARI AUV survey, 1 m");
  });
});
