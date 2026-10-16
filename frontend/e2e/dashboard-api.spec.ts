import { expect, test, type ConsoleMessage, type Page } from "@playwright/test";

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

const evaluations = capabilities.map((model, index) => ({
  model_id: model.model_id,
  evaluation_reference: model.evaluation_reference,
  source_digest_sha256: String(index + 1).repeat(64),
  metric_label: "Verified test metric",
  metric_value: 0.5 + index / 10,
  known_limitation: `Test-only capability limitation ${index + 1}`,
}));

async function mockApi(page: Page) {
  await page.route("**/model-evaluations.json", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ schema_version: "1", models: evaluations }),
  }));
  await page.route("http://127.0.0.1:4173/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    let payload: unknown;
    let status = 200;
    if (path === "/health") payload = { status: "ok" };
    else if (path === "/machines") payload = [machine];
    else if (path === "/capabilities/models") payload = { models: capabilities };
    else if (path === `/machines/${machine.id}`) payload = machine;
    else if (path === `/machines/${machine.id}/maintenance-reports` && route.request().method() === "GET") payload = [summary];
    else if (path === `/maintenance-reports/${report.report_id}/evidence`) payload = evidence;
    else if (path === `/maintenance-reports/${report.report_id}`) payload = report;
    else if (path.startsWith(`/machines/${machine.id}/maintenance-reports/`) && route.request().method() === "POST") {
      payload = report;
      status = 201;
    } else {
      payload = { detail: "Not found" };
      status = 404;
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
  });
}

function isKnownBrowserDriverNoise(message: ConsoleMessage) {
  const text = message.text();
  return message.type() === "warning" && text.includes("GL Driver Message") && text.includes("GPU stall due to ReadPixels");
}

function captureConsole(page: Page) {
  const problems: string[] = [];
  page.on("console", (message) => {
    if ((message.type() === "error" || message.type() === "warning") && !isKnownBrowserDriverNoise(message)) {
      problems.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  return problems;
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect.poll(() => page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  )).toBe(true);
}

test("normal API-backed dashboard keeps its read and analysis workflows", async ({ page }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await mockApi(page);
  const problems = captureConsole(page);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Stored machine analyses with verifiable provenance/i })).toBeVisible();
  await expect(page.getByText("Backend connected")).toBeVisible();
  await expect(page.getByText(/PUBLIC DEMO/)).toHaveCount(0);
  await expectNoHorizontalOverflow(page);

  await page.goto("/machines");
  await expect(page.getByRole("heading", { name: machine.name })).toBeVisible();
  await page.getByRole("heading", { name: machine.name }).click();
  await expect(page.getByRole("heading", { name: "Evidence Chain" })).toBeVisible();
  await expect(page.getByText("91.0%")).toBeVisible();
  await page.getByRole("button", { name: "Run Analysis" }).click();
  await expect(page.getByRole("dialog", { name: "Run Analysis" })).toBeVisible();
  const samples = page.getByRole("textbox", { name: /Time-series samples/ });
  await expect(samples).toHaveValue("");
  await expect(page.getByText(/no sample values are invented by the dashboard/i)).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();

  await page.goto("/reports");
  await expect(page.locator(".report-index__row")).toHaveCount(1);
  await page.locator(".report-index__row").click();
  await expect(page.getByRole("heading", { name: "Evidence Package" })).toBeVisible();
  await expect(page.getByText(/they are not commands, urgency ratings, or authorization/i)).toBeVisible();

  await page.goto("/models");
  await expect(page.getByText("Rejected Experiment", { exact: true })).toBeVisible();
  await expect(page.getByText("Experimental", { exact: true })).toBeVisible();
  await expect(page.getByText("Validated Baseline", { exact: true })).toBeVisible();
  await expect(page.getByText("Verified test metric", { exact: true })).toHaveCount(capabilities.length);
  await expectNoHorizontalOverflow(page);
  expect(problems).toEqual([]);
});

test("normal API errors remain calm and omit backend details", async ({ page }) => {
  await page.route("http://127.0.0.1:4173/api/**", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "SQLAlchemy traceback at C:\\private\\database" }),
    });
  });
  await page.goto("/machines");
  await expect(page.getByRole("alert")).toContainText("The server could not safely complete this request.");
  await expect(page.getByRole("alert")).not.toContainText(/SQLAlchemy|traceback|C:\\private/i);
});

test("history never attributes a previous machine's reports to a failed selection", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const machineB = { id: "33333333-3333-4333-8333-333333333333", name: "Compressor South", asset_type: "rotating_equipment" };
  const summaryA = { ...summary, executive_summary: "Machine A stored report" };
  let bUnavailable = true;
  let bRequests = 0;

  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    let status = 200;
    let payload: unknown;
    if (path === "/health") payload = { status: "ok" };
    else if (path === "/machines") payload = [machine, machineB];
    else if (path === `/machines/${machine.id}/maintenance-reports`) payload = [summaryA];
    else if (path === `/machines/${machineB.id}/maintenance-reports`) {
      bRequests += 1;
      if (bUnavailable) {
        status = 503;
        payload = { detail: "Database unavailable at C:\\private\\database" };
      } else payload = [];
    } else {
      status = 404;
      payload = { detail: "Not found" };
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
  });

  await page.goto("/reports");
  await expect(page.locator(".report-index__row")).toContainText("Machine A stored report");
  await page.getByLabel("Machine history").selectOption(machineB.id);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.locator(".report-index__row")).toHaveCount(0);
  await expect(page.getByText("1 stored report on this page", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("alert")).toContainText(machineB.name);
  await expect(page.getByRole("alert")).toContainText("History unavailable");
  await expect(page.getByRole("alert")).not.toContainText(/Database unavailable|C:\\private/i);
  await page.getByRole("alert").evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished));
  });
  await page.screenshot({ path: testInfo.outputPath("history-machine-b-error-1280.png"), fullPage: true });

  bUnavailable = false;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("heading", { name: "No reports yet" })).toBeVisible();
  await expect(page.locator(".report-index__row")).toHaveCount(0);
  expect(bRequests).toBe(2);

  await page.getByLabel("Machine history").selectOption(machine.id);
  await expect(page.locator(".report-index__row")).toContainText("Machine A stored report");
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("history ignores late superseded responses and keeps report navigation bound to the selected machine", async ({ page }) => {
  const machineB = { id: "33333333-3333-4333-8333-333333333333", name: "Compressor South", asset_type: "rotating_equipment" };
  const summaryA = { ...summary, executive_summary: "Machine A stored report" };
  const reportB = { ...report, report_id: "44444444-4444-4444-8444-444444444444", machine_id: machineB.id, narrative: { ...report.narrative, executive_summary: "Machine B stored report" } };
  const summaryB = { ...summary, report_id: reportB.report_id, machine_id: machineB.id, executive_summary: "Machine B stored report" };
  const evidenceB = { ...evidence, report: { ...evidence.report, report_id: reportB.report_id }, analysis: { ...evidence.analysis, machine_id: machineB.id } };
  let releaseA!: () => void;
  let releaseB!: () => void;
  let notifyA!: () => void;
  let notifyB!: () => void;
  let notifyASettled!: () => void;
  let notifyBSettled!: () => void;
  const aRequested = new Promise<void>((resolve) => { notifyA = resolve; });
  const bRequested = new Promise<void>((resolve) => { notifyB = resolve; });
  const aSettled = new Promise<void>((resolve) => { notifyASettled = resolve; });
  const bSettled = new Promise<void>((resolve) => { notifyBSettled = resolve; });
  const aGate = new Promise<void>((resolve) => { releaseA = resolve; });
  const bGate = new Promise<void>((resolve) => { releaseB = resolve; });
  let holdFirstA = true;
  let holdNextB = false;

  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    let payload: unknown;
    let status = 200;
    let delayed: "A" | "B" | null = null;
    if (path === "/health") payload = { status: "ok" };
    else if (path === "/machines") payload = [machine, machineB];
    else if (path === `/machines/${machine.id}/maintenance-reports`) {
      if (holdFirstA) {
        holdFirstA = false;
        delayed = "A";
        notifyA();
        await aGate;
      }
      payload = [summaryA];
    } else if (path === `/machines/${machineB.id}/maintenance-reports`) {
      if (holdNextB) {
        holdNextB = false;
        delayed = "B";
        notifyB();
        await bGate;
      }
      payload = [summaryB];
    } else if (path === `/maintenance-reports/${reportB.report_id}`) payload = reportB;
    else if (path === `/maintenance-reports/${reportB.report_id}/evidence`) payload = evidenceB;
    else {
      status = 404;
      payload = { detail: "Not found" };
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) }).catch(() => {
      // The browser may already have aborted this superseded request.
    });
    if (delayed === "A") notifyASettled();
    if (delayed === "B") notifyBSettled();
  });

  await page.goto("/reports");
  await aRequested;
  await page.getByLabel("Machine history").selectOption(machineB.id);
  await expect(page.locator(".report-index__row")).toContainText("Machine B stored report");
  releaseA();
  await aSettled;
  await expect(page.locator(".report-index__row")).toContainText("Machine B stored report");
  await expect(page.getByRole("alert")).toHaveCount(0);

  await page.getByLabel("Machine history").selectOption(machine.id);
  await expect(page.locator(".report-index__row")).toContainText("Machine A stored report");
  holdNextB = true;
  await page.getByLabel("Machine history").selectOption(machineB.id);
  await bRequested;
  await expect(page.getByText("Loading stored maintenance reports…")).toBeVisible();
  await expect(page.locator(".report-index__row")).toHaveCount(0);
  await page.getByLabel("Machine history").selectOption(machine.id);
  await expect(page.locator(".report-index__row")).toContainText("Machine A stored report");
  releaseB();
  await bSettled;
  await expect(page.locator(".report-index__row")).toContainText("Machine A stored report");
  await expect(page.getByRole("alert")).toHaveCount(0);

  await page.getByLabel("Machine history").selectOption(machineB.id);
  await expect(page.locator(".report-index__row")).toContainText("Machine B stored report");
  await page.locator(".report-index__row").click();
  await expect(page).toHaveURL(new RegExp(`/reports/${reportB.report_id}$`));
  await expect(page.getByText("Machine B stored report")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence Package" })).toBeVisible();
});
