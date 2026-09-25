import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { askBundle } from "../test/fixtures/ask/bundle.js";
import eruption from "../test/fixtures/ask/eruption.json";
import inflation2 from "../test/fixtures/ask/inflation.v2.json";
import quakes2 from "../test/fixtures/ask/quakes.v2.json";
import quakesToday from "../test/fixtures/ask/quakes.today.json";
import AskPanel, { SUGGESTIONS } from "./AskPanel.jsx";

const bundle = askBundle();
const ok = body => ({ ok: true, status: 200, json: async () => body });
const calls = { select: [], shown: [] };

// App's side of the shared ask state: the evidence on the map and the active (selected) and hovered numbers.
function Harness({ blocked = false, onOpenChange }) {
  const [ask, setAsk] = useState({ evidence: null, activeN: null, hoverN: null });
  return (
    <>
      <output data-testid="state">{JSON.stringify({ shown: ask.evidence?.id ?? null, n: ask.evidence?.located.length ?? null, activeN: ask.activeN, hoverN: ask.hoverN })}</output>
      <AskPanel bundle={bundle} evidence={ask.evidence} activeN={ask.activeN} hoverN={ask.hoverN} keysBlocked={blocked} onOpenChange={onOpenChange}
        onShow={ev => { calls.shown.push(ev); setAsk({ evidence: ev, activeN: null, hoverN: null }); }}
        onHover={n => setAsk(a => ({ ...a, hoverN: n }))}
        onSelect={n => { calls.select.push(n); setAsk(a => ({ ...a, activeN: n })); }} />
    </>
  );
}
const state = () => JSON.parse(screen.getByTestId("state").textContent);
async function askIt(q) {
  fireEvent.change(screen.getByRole("textbox", { name: /Ask/ }), { target: { value: q } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
}

beforeEach(() => { localStorage.clear(); calls.select = []; calls.shown = []; });
afterEach(() => vi.unstubAllGlobals());

describe("AskPanel", () => {
  it("asks, shows the question as a headline, then the answer with numbered citations and the evidence table", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok(inflation2)));
    render(<Harness />);
    await askIt("What's been measuring Axial's inflation before the next eruption?");
    expect(screen.getByRole("heading", { name: "What's been measuring Axial's inflation before the next eruption?" })).toBeInTheDocument();
    expect(screen.getByText("Reading the corpus…")).toBeInTheDocument();
    expect(state().shown).toBeNull();   // the map waits for the answer
    await waitFor(() => expect(screen.getByText(/which record the seafloor rising/)).toBeInTheDocument());
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({ query: expect.stringMatching(/^What's been/), answer_mode: "evidence", model: "auto" });
    expect(state()).toMatchObject({ n: 5 });
    expect(screen.getByText(/^5 on the map · 1 document · [\d.]+ s · gemini-2\.5-flash$/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Evidence on the map" });
    expect(within(table).getAllByRole("row")).toHaveLength(6);
    expect(within(table).getByText("BOTPTA303")).toBeInTheDocument();
    expect(within(table).getByText("Intl District")).toBeInTheDocument();
    expect(within(table).getByText("1,550 m")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Source 2: International District/ })).toHaveTextContent("2");
    expect(screen.getByRole("link", { name: "Eruption forecasts at Axial Seamount ↗" })).toHaveAttribute("href", "https://axial.ceoas.oregonstate.edu/axial_blog.html");
  });

  it("hover sets the highlighted item, click selects it, the active row opens its excerpt", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok(inflation2)));
    render(<Harness />);
    await askIt("inflation?");
    const sup = await screen.findByRole("button", { name: /^Source 2:/ });
    fireEvent.mouseEnter(sup);
    expect(state().hoverN).toBe(2);
    fireEvent.mouseLeave(sup);
    expect(state().hoverN).toBeNull();
    fireEvent.click(sup);
    expect(state().activeN).toBe(2);
    expect(screen.getByText("PMEL/Chadwick PMELcabled BPR/Tilt · pressure")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("row", { name: /^4 AXCC1/ }));
    expect(state().activeN).toBe(4);
    expect(screen.getByText("4 / 5")).toBeInTheDocument();
  });

  it("a cited range of three or more is one superscript; hover and click take its first number", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok({ ...inflation2, answer: "All of them record the uplift [1-5], two agree [1-2]." })));
    render(<Harness />);
    await askIt("inflation?");
    const range = await screen.findByRole("button", { name: /^Sources 1–5:/ });
    expect(range).toHaveTextContent(/^1–5$/);
    expect(screen.queryByRole("button", { name: /^Source 3:/ })).toBeNull();
    expect(screen.getAllByRole("button", { name: /^Source [12]:/ })).toHaveLength(2);
    fireEvent.mouseEnter(range);
    expect(state().hoverN).toBe(1);
    fireEvent.mouseLeave(range);
    fireEvent.click(range);
    expect(state().activeN).toBe(1);
  });

  it("← / → and the stepper tour the evidence in order; Escape clears the card, then the evidence", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok(inflation2)));
    render(<Harness />);
    await askIt("inflation?");
    await screen.findByRole("table", { name: "Evidence on the map" });
    fireEvent.click(screen.getByRole("button", { name: "Next evidence" }));
    expect(state().activeN).toBe(1);
    act(() => { document.body.focus(); });
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(state().activeN).toBe(2);
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(state().activeN).toBe(5);   // wraps
    fireEvent.keyDown(window, { key: "Escape" });
    expect(state()).toMatchObject({ activeN: null, n: 5 });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(state().shown).toBeNull();
  });

  it("arrows pan the map unless a tour is on; keys are left alone while a side panel is open or while typing in a field", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok(inflation2)));
    const { rerender } = render(<Harness />);
    await askIt("inflation?");
    await screen.findByRole("table", { name: "Evidence on the map" });
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(state().activeN).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Next evidence" }));
    rerender(<Harness blocked />);
    fireEvent.keyDown(window, { key: "ArrowRight" });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(state().activeN).toBe(1);
  });

  it("the Worker being down is one line with Retry, and the map is untouched", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 503, json: async () => ({ error: "answer temporarily unavailable" }) })));
    render(<Harness />);
    await askIt("Where can I download the BPR record?");
    await screen.findByText("Answer temporarily unavailable (HTTP 503).");
    expect(state().shown).toBeNull();
    fetch.mockImplementation(async () => ok(eruption));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByText(/No mapped instruments in this answer/);
    expect(state()).toMatchObject({ n: 0 });
    expect(screen.getAllByRole("link", { name: /↗$/ })).toHaveLength(6);
  });

  it("the empty state offers the demo questions in order; one click asks", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok(quakesToday)));
    render(<Harness />);
    expect(SUGGESTIONS).toEqual([
      "What instruments are on Southern Hydrate Ridge?",
      "Which instruments measure dissolved oxygen?",
      "How do I get the DAS data?",
      "How many earthquakes at Axial today?",
    ]);
    expect(screen.getAllByRole("button", { name: /\?$/ }).map(b => b.textContent)).toEqual(SUGGESTIONS);
    fireEvent.click(screen.getByRole("button", { name: "How many earthquakes at Axial today?" }));
    await screen.findByRole("table", { name: "Earthquakes on the map" });
    expect(JSON.parse(fetch.mock.calls[0][1].body).query).toBe("How many earthquakes at Axial today?");
    expect(screen.getByText(/^4 earthquakes · 2026-09-25 UTC · [\d.]+ s · live catalog$/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "How many earthquakes at Axial today?" })).toBeNull();
  });

  it("earlier answers stay in the thread; clicking one shows its evidence again", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok(inflation2)));
    render(<Harness />);
    await askIt("first?");
    await screen.findByRole("table", { name: "Evidence on the map" });
    const first = state().shown;
    fetch.mockImplementation(async () => ok(eruption));
    await askIt("second?");
    await screen.findByText(/No mapped instruments/);
    expect(state().shown).not.toBe(first);
    fireEvent.click(screen.getByRole("button", { name: "Show the evidence for: first?" }));
    expect(state()).toMatchObject({ shown: first, n: 5 });
  });

  it("minimizes to a tab, keeps the thread, remembers, and sets the left inset", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok(eruption)));
    const onOpenChange = vi.fn();
    const { unmount } = render(<Harness onOpenChange={onOpenChange} />);
    const css = n => document.documentElement.style.getPropertyValue(n);
    expect(css("--left-inset")).toBe("412px");
    await askIt("hello there");
    await screen.findByText(/No mapped instruments/);
    fireEvent.click(screen.getByRole("button", { name: "Minimize Ask Atlas" }));
    expect(css("--left-inset")).toBe("16px");
    expect(css("--strip-reserve")).not.toBe("0px");
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
    fireEvent.click(screen.getByRole("button", { name: "Open Ask Atlas" }));
    expect(screen.getByRole("heading", { name: "hello there" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Minimize Ask Atlas" }));
    unmount();
    render(<Harness />);
    expect(screen.getByRole("button", { name: "Open Ask Atlas" })).toBeInTheDocument();
  });

  it("offers the Worker's models", () => {
    render(<Harness />);
    const pick = screen.getByRole("combobox", { name: "Answer model" });
    expect(within(pick).getAllByRole("option").map(o => o.value)).toContain("groq-gpt-oss-120b");
    expect(pick).toHaveValue("auto");
  });
});
