import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library only auto-cleans when afterEach is a global; vitest runs without globals.
afterEach(cleanup);
