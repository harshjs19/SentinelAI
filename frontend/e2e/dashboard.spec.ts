import { expect, test, type Page } from "@playwright/test";

import { capabilities, evidence, machine, report } from "../src/test/fixtures";

const summary = {
  report_id: report.report_id,
  machine_id: machine.id,
  generated_at: report.generated_at,
  generation_status: report.generation_status,
  condition: report.analysis.condition,
  analysis_status: report.analysis.status,
  executive_summary: report.narrative.executive_summary,
};

async function mockApi(page: Page, options: { emptyHistory?: boolean } = {}) {
  await page.route("http://127.0.0.1:4173/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    let payload: unknown;
    let status = 200;
    if (path === "/health") payload = { status: "ok" };
    else if (path === "/machines") payload = [machine];
    else if (path === "/capabilities/models") payload = { models: capabilities };
    else if (path === `/machines/${machine.id}`) payload = machine;
    else if (path === `/machines/${machine.id}/maintenance-reports` && route.request().method() === "GET") payload = options.emptyHistory ? [] : [summary];
    else if (path === `/maintenance-reports/${report.report_id}/evidence`) payload = evidence;
    else if (path === `/maintenance-reports/${report.report_id}`) payload = report;
    else if (path.startsWith(`/machines/${machine.id}/maintenance-reports/`) && route.request().method() === "POST") { payload = report; status = 201; }
    else { payload = { detail: "Not found" }; status = 404; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
  });
}

function captureConsole(page: Page) {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") problems.push(`${message.type()}: ${message.text()}`);
  });
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  return problems;
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
}

test("all major dashboard views are usable and console-clean", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await mockApi(page);
  const problems = captureConsole(page);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Industrial intelligence grounded/i })).toBeVisible();
  await expect(page.getByText(/Independent analysis modules/)).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("overview-1440.png"), fullPage: true });

  await page.getByRole("link", { name: "Machines" }).click();
  await expect(page.getByRole("heading", { name: machine.name })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("machines-1440.png"), fullPage: true });

  await page.getByRole("heading", { name: machine.name }).click();
  await expect(page.getByText("Raw model confidence — not failure probability.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence Chain" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("machine-report-1440.png"), fullPage: true });

  await page.getByRole("button", { name: /Run Analysis/i }).click();
  await expect(page.getByRole("dialog", { name: "Run Analysis" })).toBeVisible();
  await expect(page.getByText("Synthetic/demo values are prefilled.")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("analysis-drawer-1440.png"), fullPage: true });
  await page.getByRole("button", { name: "Close", exact: true }).click();

  await page.getByRole("link", { name: "Maintenance Reports" }).click();
  const storedReportLink = page.locator(".report-index__row").first();
  await expect(storedReportLink).toContainText(report.narrative.executive_summary);
  await storedReportLink.click();
  await expect(page.getByRole("heading", { name: "Evidence Package" })).toBeVisible();
  await page.getByRole("button", { name: new RegExp(report.citations[0].title) }).click();
  await expect(page.getByText("Evidence interpretation")).toBeVisible();
  await page.getByRole("heading", { name: "Evidence Chain" }).scrollIntoViewIfNeeded();
  await page.waitForTimeout(350);
  await page.screenshot({ path: testInfo.outputPath("report-evidence-1440.png") });

  await page.getByRole("link", { name: "Model Capabilities" }).click();
  await expect(page.getByText("Rejected Experiment", { exact: true })).toBeVisible();
  await expect(page.getByText("Experimental", { exact: true })).toBeVisible();
  await page.getByText("audio_ast_rejected_v1").click();
  await expect(page.getByText(/Preserved as a rejected experimental result/i)).toBeVisible();
  await page.waitForTimeout(300);
  await page.screenshot({ path: testInfo.outputPath("models-1440.png"), fullPage: true });

  expect(problems).toEqual([]);
});

test("tablet, reduced-motion, empty-history, and WebGL fallback remain usable", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (contextId: string, ...args: unknown[]) {
      if (contextId === "webgl" || contextId === "experimental-webgl" || contextId === "webgl2") return null;
      return original.call(this, contextId as never, ...(args as []));
    } as typeof HTMLCanvasElement.prototype.getContext;
  });
  await mockApi(page, { emptyHistory: true });
  const problems = captureConsole(page);
  await page.goto("/");
  await expect(page.locator(".static-core:not(.static-core--loading)")).toBeVisible();
  const reducedDurationMs = await page.locator(".ambient-canvas__glow").first().evaluate((element) => {
    const value = getComputedStyle(element).animationDuration;
    return value.endsWith("ms") ? Number.parseFloat(value) : Number.parseFloat(value) * 1000;
  });
  expect(reducedDurationMs).toBeLessThanOrEqual(0.001);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("overview-tablet-webgl-fallback.png"), fullPage: true });

  await page.goto(`/machines/${machine.id}`);
  await expect(page.getByRole("heading", { name: "No reports yet" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.getByRole("button", { name: /Run Analysis/i }).first().click();
  await expect(page.getByRole("dialog", { name: "Run Analysis" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("analysis-tablet.png"), fullPage: true });
  expect(problems).toEqual([]);
});

test("1024 workspace preserves premium hierarchy and evidence legibility", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1024, height: 900 });
  await mockApi(page);
  const problems = captureConsole(page);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Industrial intelligence grounded/i })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("overview-1024.png"), fullPage: true });

  await page.goto(`/reports/${report.report_id}`);
  const chain = page.getByRole("heading", { name: "Evidence Chain" });
  await chain.scrollIntoViewIfNeeded();
  await expect(chain).toBeVisible();
  await page.waitForTimeout(800);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("report-evidence-1024.png") });

  expect(problems).toEqual([]);
});

test("laptop report layout tolerates long identifiers, citations, and report text", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockApi(page);
  const problems = captureConsole(page);
  await page.goto(`/reports/${report.report_id}`);
  await expect(page.getByText(report.citations[0].title)).toBeVisible();
  await expect(page.getByText("sentence-transformers/all-MiniLM-L6-v2").first()).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("report-1280.png"), fullPage: true });
  expect(problems).toEqual([]);
});
