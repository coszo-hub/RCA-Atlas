import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:5175", viewport: { width: 1600, height: 1000 },
         launchOptions: { args: ["--use-angle=metal", "--ignore-gpu-blocklist"] } },
  webServer: { command: "npx vite --port 5175 --strictPort", url: "http://127.0.0.1:5175", reuseExistingServer: true, timeout: 60_000 },
});
