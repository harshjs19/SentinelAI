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
