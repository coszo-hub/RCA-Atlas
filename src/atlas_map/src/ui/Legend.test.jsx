import { render } from "@testing-library/react";
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
