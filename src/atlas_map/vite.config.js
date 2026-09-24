import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxy = { "/api": { target: "http://127.0.0.1:8787", rewrite: p => p.replace(/^\/api/, "") } };

// A build uses relative URLs so it runs from any folder (coszo.org serves it at /rca-atlas/map/); dev and tests stay at "/".
export default defineConfig(({ command }) => ({
  base: command === "build" ? "./" : "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5175,
    proxy: apiProxy,
  },
  preview: { proxy: apiProxy },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.js"],
    include: ["src/**/*.test.{js,jsx}"],
  },
}));
