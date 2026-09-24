import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Ask Atlas answers come from the RCA Atlas Worker, which only accepts requests from coszo.org. In development
// /api/ask goes there (or to `wrangler dev` with VITE_ATLAS_ASK=http://127.0.0.1:8788) with that Origin. It is listed
// before /api, the local live-data gateway, so it matches first.
const askTarget = loadEnv("development", process.cwd(), "VITE_ATLAS_ASK").VITE_ATLAS_ASK || "https://rca-atlas.quakehunt.workers.dev";
const apiProxy = {
  "/api/ask": { target: askTarget, changeOrigin: true, rewrite: () => "/v1/answer",
    configure: proxy => proxy.on("proxyReq", req => req.setHeader("origin", "https://coszo.org")) },
  "/api": { target: "http://127.0.0.1:8787", rewrite: p => p.replace(/^\/api/, "") },
};

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
