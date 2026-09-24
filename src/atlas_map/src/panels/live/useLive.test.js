import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useLive } from "./useLive.js";

describe("useLive", () => {
  it("a slow response for an old key never renders under the new key", async () => {
    let resolveA;
    const slowA = () => new Promise(r => { resolveA = r; });   // ignores abort, like a slow network
    const fastB = async () => ({ ok: true, data: "B" });
    const seen = [];
    const { result, rerender } = renderHook(({ k }) => {
      const r = useLive(k, k === "A" ? slowA : fastB);
      seen.push([k, r.state, r.data]);
      return r;
    }, { initialProps: { k: "A" } });
    rerender({ k: "B" });
    await waitFor(() => expect(result.current.data).toBe("B"));
    await act(async () => { resolveA({ ok: true, data: "A" }); });
    expect(result.current.data).toBe("B");
    expect(seen.filter(([k, , d]) => k === "B" && d === "A")).toEqual([]);
  });
  it("never shows the previous key's data during the switch", async () => {
    const seen = [];
    const { result, rerender } = renderHook(({ k }) => {
      const r = useLive(k, async () => ({ ok: true, data: k }));
      seen.push([k, r.data]);
      return r;
    }, { initialProps: { k: "A" } });
    await waitFor(() => expect(result.current.data).toBe("A"));
    rerender({ k: "B" });
    await waitFor(() => expect(result.current.data).toBe("B"));
    expect(seen.filter(([k, d]) => k === "B" && d === "A")).toEqual([]);
  });
});
