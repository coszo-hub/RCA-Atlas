import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import FileBrowser from "./FileBrowser.jsx";

afterEach(() => vi.unstubAllGlobals());

const route = { kind: "pi_portal", label: "PI data portal", instrumentKey: "K1", endpointId: "e1", url: "https://pi.example.org/k1/" };
const listing = (entries, extra = {}) => ({ instrumentKey: "K1", endpointLabel: "PI data portal", path: "", sourceUrl: null,
  entries, truncated: false, message: null, ...extra });
const dir = (name, path) => ({ name, kind: "directory", path, url: `https://pi.example.org/k1/${path}`, date: null });
const file = (name, path) => ({ name, kind: "file", path, url: `https://pi.example.org/files/${path}`, date: "2026-09-20" });

// Answers by the `path` query parameter.
const byPath = pages => vi.fn(async url => {
  const p = new URL(String(url), "http://x").searchParams.get("path") ?? "";
  return { ok: true, status: 200, json: async () => pages[p] };
});
const pathsRequested = f => f.mock.calls.map(([u]) => new URL(String(u), "http://x").searchParams.get("path") ?? "");

describe("FileBrowser", () => {
  it("opens a directory by its entry path and goes back Up", async () => {
    const f = byPath({
      "": listing([dir("2026", "2026/")]),
      "2026/": listing([dir("09", "2026/09/")], { path: "2026/" }),
      "2026/09/": listing([file("a.csv", "2026/09/a.csv")], { path: "2026/09/" }),
    });
    vi.stubGlobal("fetch", f);
    render(<FileBrowser route={route} />);
    fireEvent.click(await screen.findByRole("button", { name: "2026/" }));
    fireEvent.click(await screen.findByRole("button", { name: "09/" }));
    await screen.findByRole("link", { name: "a.csv" });
    expect(pathsRequested(f)).toEqual(["", "2026/", "2026/09/"]);
    fireEvent.click(screen.getByRole("button", { name: "Up" }));
    await screen.findByRole("button", { name: "09/" });
    expect(pathsRequested(f).at(-1)).toBe("2026/");
    fireEvent.click(screen.getByRole("button", { name: "Up" }));
    await screen.findByRole("button", { name: "2026/" });
    expect(screen.queryByRole("button", { name: "Up" })).toBeNull();
  });

  it("links files to the entry url in a new tab", async () => {
    vi.stubGlobal("fetch", byPath({ "": listing([file("b.nc", "b.nc")]) }));
    render(<FileBrowser route={route} />);
    const a = await screen.findByRole("link", { name: "b.nc" });
    expect(a).toHaveAttribute("href", "https://pi.example.org/files/b.nc");
    expect(a).toHaveAttribute("target", "_blank");
  });

  it("says when only the newest 200 entries are shown", async () => {
    vi.stubGlobal("fetch", byPath({ "": listing([file("c.csv", "c.csv")], { truncated: true }) }));
    render(<FileBrowser route={route} />);
    expect(await screen.findByText("Showing the newest 200 entries.")).toBeInTheDocument();
  });

  it("an upstream truncation message replaces the 200-entries line", async () => {
    const message = "This folder has more than 5,000 entries; the newest may be missing. Open the folder on the PI portal to see everything.";
    vi.stubGlobal("fetch", byPath({ "": listing([file("d.csv", "d.csv")], { truncated: true, message }) }));
    render(<FileBrowser route={route} />);
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.queryByText("Showing the newest 200 entries.")).toBeNull();
  });
});
