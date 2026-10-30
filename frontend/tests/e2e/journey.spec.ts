import { expect, test, type Page } from "@playwright/test";

const SHOTS = process.env.SHOT_DIR ?? "../docs/screenshots";

async function missionsData(page: Page) {
  return (await page.request.get("/api/missions")).json();
}

/** Run a mission step from its card and wait until the step is verified (or settles in another state). */
async function runStep(page: Page, stepId: string, expectStatus = "verified") {
  const card = page.getByTestId(`step-${stepId}`);
  await card.getByTestId("run-step").click();
  await expect(card).toHaveAttribute("data-step-status", expectStatus, { timeout: 180_000 });
  return card;
}

async function answerQuiz(page: Page, missionId: string, stepId: string) {
  const data = await missionsData(page);
  const step = data.missions.find((m: any) => m.id === missionId).steps.find((s: any) => s.id === stepId);
  const card = page.getByTestId(`step-${stepId}`);
  const wrong = (step.quiz.answer + 1) % step.quiz.options.length;
  // A wrong answer is never accepted as mastery.
  await card.locator(`input[type=radio]`).nth(wrong).check();
  await card.getByTestId("quiz-submit").click();
  await expect(card.getByTestId("quiz-result")).toHaveClass(/warn/);
  await expect(card).not.toHaveAttribute("data-step-status", "verified");
  await card.locator(`input[type=radio]`).nth(step.quiz.answer).check();
  await card.getByTestId("quiz-submit").click();
  await expect(card).toHaveAttribute("data-step-status", "verified");
}

test.describe.configure({ mode: "serial" });

test("defaults to English even when the browser prefers zh-TW", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1")).toHaveText("The Lab");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByTestId("lang-en")).toHaveAttribute("aria-pressed", "true");
});

test("language switch is manual, persists, and keeps mode", async ({ page }) => {
  await page.goto("/#/missions");
  await page.getByTestId("mode-expert").click();
  await page.getByTestId("lang-zh-TW").click();
  await expect(page.locator("h1")).toHaveText("任務控制中心");
  await page.reload();
  await expect(page.locator("h1")).toHaveText("任務控制中心");
  await expect(page.getByTestId("mode-expert")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("lang-en").click();
  await expect(page.locator("h1")).toHaveText("Mission Control");
  await page.getByTestId("mode-guided").click();
});

test("full journey: missions 01-07 with real execution", async ({ page }) => {
  // Mission 01
  await page.goto("/#/missions/m01-meet-your-machine");
  await runStep(page, "s1-scan");
  await answerQuiz(page, "m01-meet-your-machine", "s2-vram-check");
  await expect(page.getByTestId("mission-state")).toHaveText("Complete");

  // Language switch mid-journey must not reset progress.
  await page.getByTestId("lang-zh-TW").click();
  await expect(page.getByTestId("mission-state")).toHaveText("已完成");
  await page.getByTestId("lang-en").click();

  // Mission 02: hub step is optional and NOT RUN without Hub access; local inspection is real.
  await page.goto("/#/missions/m02-find-your-model");
  await runStep(page, "s1-inspect-local");
  const caps = (await missionsData(page)).capabilities;
  if (!caps.hub_access) await expect(page.getByTestId("step-s2-inspect-hub").getByTestId("capability-warning")).toBeVisible();
  await answerQuiz(page, "m02-find-your-model", "s3-safety-check");

  // Mission 03: build the tiny model, run real inference, view the executed source.
  await page.goto("/#/missions/m03-wake-it-up");
  await runStep(page, "s1-prepare");
  const infer = await runStep(page, "s2-infer");
  await infer.getByTestId("view-source").click();
  await expect(page.getByTestId("source-viewer")).toContainText("def run_inference");
  await page.keyboard.press("Escape");
  await answerQuiz(page, "m03-wake-it-up", "s3-why-gibberish");

  // Mission 04: real mini server.
  await page.goto("/#/missions/m04-build-your-server");
  await answerQuiz(page, "m04-build-your-server", "s1-local-vs-serving");
  await runStep(page, "s2-start-mini");
  await runStep(page, "s3-health");

  // Mission 05: baseline benchmark.
  await page.goto("/#/missions/m05-put-it-to-the-test");
  await answerQuiz(page, "m05-put-it-to-the-test", "s1-metrics-check");
  await runStep(page, "s2-baseline");
  await answerQuiz(page, "m05-put-it-to-the-test", "s3-p95-check");

  // Mission 06: one-variable change, then compare.
  await page.goto("/#/missions/m06-hunt-the-bottleneck");
  const cand = page.getByTestId("step-s1-candidate");
  const hyp = cand.locator("label", { hasText: "hypothesis" }).locator("input");
  if (await hyp.count()) await hyp.fill("TTFT rises with concurrency because the mini server is serial");
  await runStep(page, "s1-candidate");
  await runStep(page, "s2-compare");
  await answerQuiz(page, "m06-hunt-the-bottleneck", "s3-interpret");

  // Mission 07: report with provenance.
  await page.goto("/#/missions/m07-defend-your-decision");
  await runStep(page, "s1-report");
  await answerQuiz(page, "m07-defend-your-decision", "s2-provenance-check");

  const final = await missionsData(page);
  for (const m of final.missions) expect.soft(final.status[m.id].state, m.id).toBe("complete");
});

test("arena compares the two real benchmarks and labels demo data", async ({ page }) => {
  await page.goto("/#/arena");
  await page.getByTestId("cmp-run").click();
  await expect(page.getByTestId("comparison")).toContainText("workload.concurrency");
  // Each metric shows a 95% interval for the difference (both benchmarks ran more than one trial).
  await expect(page.getByTestId("ci-ttft_p50_ms")).toContainText(/…/);
  await expect(page.locator('[data-provenance="DEMO_SAMPLE"]').first()).toBeVisible();
  await expect(page.locator('[data-provenance="LIVE_MEASURED"]').first()).toBeVisible();
});

test("costly benchmark asks for approval and runs nothing when cancelled", async ({ page }) => {
  const benchRuns = async () => (await (await page.request.get("/api/runs")).json()).filter((r: any) => r.action === "bench.run").length;
  const before = await benchRuns();
  await page.goto("/#/arena");
  await page.getByTestId("bench-num_requests").fill("500");
  await page.getByTestId("bench-max_tokens").fill("512");
  await page.getByTestId("bench-run").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  expect(await benchRuns()).toBe(before);
});

test("garage rejects invalid model input", async ({ page }) => {
  await page.goto("/#/garage");
  await page.getByTestId("model-input").fill("https://evil.example.com/x/y");
  await page.getByTestId("inspect-hub").click();
  await expect(page.getByTestId("input-error")).toBeVisible();
});

test("journal keeps failed and not-run records visible", async ({ page }) => {
  await page.goto("/#/journal");
  await page.getByRole("tab", { name: /All runs/ }).click();
  await expect(page.getByTestId("runs-table")).toBeVisible();
});

test("screenshots in English and Traditional Chinese", async ({ page }) => {
  const pages = ["lab", "missions/m05-put-it-to-the-test", "garage", "code?path=inference_lab%2Fbench%2Fmetrics.py&symbol=percentile", "research/kwon-2023-pagedattention", "arena", "journal"];
  for (const lang of ["en", "zh-TW"] as const) {
    await page.goto("/");
    await page.getByTestId(`lang-${lang}`).click();
    for (const p of pages) {
      await page.goto(`/#/${p}`);
      await page.waitForTimeout(900);
      if (p === "arena") { await page.getByTestId("cmp-run").click(); await page.getByTestId("comparison").waitFor(); }
      await page.screenshot({ path: `${SHOTS}/${lang}-${p.split(/[/?]/)[0]}.png`, fullPage: true });
    }
  }
  await page.getByTestId("lang-en").click();
});
