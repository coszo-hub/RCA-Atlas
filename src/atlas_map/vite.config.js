import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxy = { "/api": { target: "http://127.0.0.1:8787", rewrite: p => p.replace(/^\/api/, "") } };

export default defineConfig({
  // The public atlas is served below /rca-atlas/map2/, not at the custom-domain root.
  // Relative asset URLs keep both the Pages deployment and local preview portable.
  base: "./",
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
});
