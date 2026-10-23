import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

// Runs against the real backend (`inference-lab ui`) with a throwaway data directory.
// Uses the pre-installed Chromium when present; set PW_CHROMIUM to override.
const home = process.env.E2E_LAB_HOME ?? join(tmpdir(), "inference-lab-e2e");
const win = process.platform === "win32";
const labBin = win ? `"${resolve("..", ".venv", "Scripts", "inference-lab.exe")}"` : "../.venv/bin/inference-lab";
// Linux CI image ships Chromium at /opt/pw-browsers; elsewhere use Playwright's own browser.
const chromium = process.env.PW_CHROMIUM ?? (existsSync("/opt/pw-browsers/chromium") ? "/opt/pw-browsers/chromium" : undefined);
const serverCmd = win
  ? `node -e "require('fs').rmSync(process.argv[1],{recursive:true,force:true})" "${home}" && set "INFERENCE_LAB_HOME=${home}" && ${labBin} ui`
  : `rm -rf ${home} && INFERENCE_LAB_HOME=${home} ${labBin} ui`;
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
    launchOptions: chromium ? { executablePath: chromium } : {},
  },
  webServer: {
    command: serverCmd,
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
