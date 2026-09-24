import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ChatPanel from "./ChatPanel.jsx";

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("ChatPanel", () => {
  it("asks, shows the answer with citations", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ answer: "Axial has 66 sensors.", model: "m", citations: [{ id: "1", title: "OOI", url: "https://oceanobservatories.org" }] }) })));
    render(<ChatPanel selection={{}} />);
    fireEvent.change(screen.getByRole("textbox", { name: /Ask/ }), { target: { value: "What is at Axial?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(screen.getByText("Axial has 66 sensors.")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "OOI" })).toHaveAttribute("href", "https://oceanobservatories.org");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ question: "What is at Axial?" });
  });
  it("minimizes to a tab, keeps messages, and remembers", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ answer: "A.", citations: [] }) })));
    const { unmount } = render(<ChatPanel selection={{}} />);
    fireEvent.change(screen.getByRole("textbox", { name: /Ask/ }), { target: { value: "hello there" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => screen.getByText("A."));
    fireEvent.click(screen.getByRole("button", { name: "Minimize chat" }));
    expect(screen.queryByRole("textbox", { name: /Ask/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));
    expect(screen.getByText("A.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Minimize chat" }));
    unmount();
    render(<ChatPanel selection={{}} />);
    expect(screen.getByRole("button", { name: "Open chat" })).toBeInTheDocument();
  });
  it("chat service down is stated plainly", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 502, json: async () => ({ error: { source: "Atlas chat", message: "chat service unreachable" } }) })));
    render(<ChatPanel selection={{}} />);
    fireEvent.change(screen.getByRole("textbox", { name: /Ask/ }), { target: { value: "hello there" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(screen.getByText(/The chat is unavailable/)).toBeInTheDocument());
  });
});

describe("ChatPanel layout", () => {
  it("sets the left inset and the strip reserve, and reports open state", () => {
    const onOpenChange = vi.fn();
    render(<ChatPanel selection={{}} onOpenChange={onOpenChange} />);
    const css = n => document.documentElement.style.getPropertyValue(n);
    expect(css("--left-inset")).toBe("412px");
    expect(css("--strip-reserve")).toBe("0px");
    expect(onOpenChange).toHaveBeenLastCalledWith(true);
    fireEvent.click(screen.getByRole("button", { name: "Minimize chat" }));
    expect(css("--left-inset")).toBe("16px");
    expect(css("--strip-reserve")).not.toBe("0px");
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
  });
});
