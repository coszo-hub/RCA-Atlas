import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library only auto-cleans when afterEach is a global; vitest runs without globals.
afterEach(cleanup);

// jsdom has no matchMedia; uPlot reads it when imported (device pixel ratio).
if (typeof window.matchMedia !== "function") {
  window.matchMedia = query => ({ matches: false, media: query, onchange: null,
    addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false });
}
