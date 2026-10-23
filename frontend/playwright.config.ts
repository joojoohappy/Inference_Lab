import { defineConfig } from "@playwright/test";

// Runs against the real backend (`inference-lab ui`) with a throwaway data directory.
// Uses the pre-installed Chromium when present; set PW_CHROMIUM to override.
const home = process.env.E2E_LAB_HOME ?? "/tmp/inference-lab-e2e";
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 240_000,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8765",
    viewport: { width: 1360, height: 900 },
    locale: "zh-TW", // browser says zh-TW on purpose: the app must still default to English
    launchOptions: { executablePath: process.env.PW_CHROMIUM ?? "/opt/pw-browsers/chromium" },
  },
  webServer: {
    command: `rm -rf ${home} && INFERENCE_LAB_HOME=${home} ../.venv/bin/inference-lab ui`,
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
