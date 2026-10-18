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

test("normal API Evidence Chain remains readable on a narrow phone and desktop", async ({ page }, testInfo) => {
  await mockApi(page);
  const problems = captureConsole(page);
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/reports/${report.report_id}`);
    const chain = page.locator(".evidence-chain");
    const nodes = chain.locator(".evidence-node");
    await expect(nodes).toHaveCount(5);
    await expect(chain.getByRole("heading", { name: "Evidence Chain" })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    if (width === 320) {
      await expect.poll(() => nodes.locator("strong").first().evaluate((element) => element.getBoundingClientRect().width)).toBeGreaterThan(120);
      await expect(chain.locator(".evidence-chain__architecture")).toHaveCSS("display", "none");
    }
    for (let index = 0; index < 5; index += 1) {
      await nodes.nth(index).scrollIntoViewIfNeeded();
      await expect(nodes.nth(index)).toHaveCSS("opacity", "1");
    }
    await chain.screenshot({ path: testInfo.outputPath(`normal-evidence-chain-${width}.png`), animations: "disabled" });
  }
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

test("history does not offer a terminal empty page when exactly ten reports exist", async ({ page }) => {
  const summaries = Array.from({ length: 10 }, (_, index) => ({
    ...summary,
    report_id: `report-${index + 1}`,
    executive_summary: `Stored report ${index + 1}`,
  }));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    let payload: unknown = { detail: "Not found" };
    let status = 404;
    if (path === "/health") { payload = { status: "ok" }; status = 200; }
    if (path === "/machines") { payload = [machine]; status = 200; }
    if (path === `/machines/${machine.id}/maintenance-reports`) {
      const offset = Number(url.searchParams.get("offset"));
      const limit = Number(url.searchParams.get("limit"));
      payload = summaries.slice(offset, offset + limit);
      status = 200;
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
  });

  await page.goto("/reports");
  await expect(page.locator(".report-index__row")).toHaveCount(10);
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();
  await expect(page.getByRole("heading", { name: "No reports yet" })).toHaveCount(0);
});

test("history stops on its second page when exactly twenty reports exist", async ({ page }) => {
  const summaries = Array.from({ length: 20 }, (_, index) => ({ ...summary, report_id: `report-${index + 1}` }));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    let payload: unknown = { status: "ok" };
    if (path === "/machines") payload = [machine];
    if (path.endsWith("/maintenance-reports")) {
      const offset = Number(url.searchParams.get("offset"));
      payload = summaries.slice(offset, offset + Number(url.searchParams.get("limit")));
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/reports");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Page 2")).toBeVisible();
  await expect(page.locator(".report-index__row")).toHaveCount(10);
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Previous" })).toBeEnabled();
});

test("quick Next and Previous navigation keeps the visible report window aligned", async ({ page }) => {
  const summaries = Array.from({ length: 12 }, (_, index) => ({ ...summary, report_id: `report-${index + 1}`, executive_summary: `Stored report ${index + 1}` }));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    let payload: unknown = { status: "ok" };
    if (path === "/machines") payload = [machine];
    if (path.endsWith("/maintenance-reports")) {
      const offset = Number(url.searchParams.get("offset"));
      payload = summaries.slice(offset, offset + Number(url.searchParams.get("limit")));
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/reports");
  await expect(page.locator(".report-index__row")).toHaveCount(10);
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.locator(".report-index__row")).toHaveCount(2);
  await expect(page.locator(".report-index__row").first()).toContainText("Stored report 11");
  await page.getByRole("button", { name: "Previous" }).click();
  await expect(page.locator(".report-index__row")).toHaveCount(10);
  await expect(page.locator(".report-index__row").first()).toContainText("Stored report 1");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.locator(".report-index__row").first()).toContainText("Stored report 11");
});

test("history advances to a real last page and resets for a machine with fewer reports", async ({ page }) => {
  const machineB = { id: "33333333-3333-4333-8333-333333333333", name: "Compressor South", asset_type: "rotating_equipment" };
  const summaries = Array.from({ length: 21 }, (_, index) => ({ ...summary, report_id: `report-${index + 1}`, executive_summary: `Stored report ${index + 1}` }));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    let payload: unknown = { status: "ok" };
    if (path === "/machines") payload = [machine, machineB];
    if (path.endsWith("/maintenance-reports")) {
      const records = path.includes(machineB.id) ? [
        { ...summary, machine_id: machineB.id, executive_summary: "Machine B only report" },
      ] : summaries;
      payload = records.slice(Number(url.searchParams.get("offset")), Number(url.searchParams.get("offset")) + Number(url.searchParams.get("limit")));
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/reports");
  await expect(page.locator(".report-index__row")).toHaveCount(10);
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Page 2")).toBeVisible();
  await expect(page.locator(".report-index__row")).toHaveCount(10);
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Page 3")).toBeVisible();
  await expect(page.locator(".report-index__row")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();
  await page.getByLabel("Machine history").selectOption(machineB.id);
  await expect(page.getByText("Page 1")).toBeVisible();
  await expect(page.locator(".report-index__row")).toContainText("Machine B only report");
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();
});

test("history retains Previous when reports disappear from a later page", async ({ page }) => {
  let count = 11;
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    let payload: unknown = { status: "ok" };
    if (path === "/machines") payload = [machine];
    if (path.endsWith("/maintenance-reports")) {
      const records = Array.from({ length: count }, (_, index) => ({ ...summary, report_id: `report-${index + 1}` }));
      const offset = Number(url.searchParams.get("offset"));
      payload = records.slice(offset, offset + Number(url.searchParams.get("limit")));
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/reports");
  await expect(page.getByRole("button", { name: "Next" })).toBeEnabled();
  count = 9;
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("heading", { name: "No reports on this page" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No reports yet" })).toHaveCount(0);
  await page.getByRole("button", { name: "Previous" }).click();
  await expect(page.locator(".report-index__row")).toHaveCount(9);
});

test("history retries a failed later page without changing machine or offset", async ({ page }) => {
  const summaries = Array.from({ length: 11 }, (_, index) => ({ ...summary, report_id: `report-${index + 1}` }));
  let failLaterPage = true;
  const requestedOffsets: number[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    let payload: unknown = { status: "ok" };
    let status = 200;
    if (path === "/machines") payload = [machine];
    if (path === `/machines/${machine.id}/maintenance-reports`) {
      const offset = Number(url.searchParams.get("offset"));
      requestedOffsets.push(offset);
      if (offset === 10 && failLaterPage) {
        status = 503;
        payload = { detail: "Database unavailable at C:\\private\\database" };
      } else payload = summaries.slice(offset, offset + Number(url.searchParams.get("limit")));
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/reports");
  await expect(page.locator(".report-index__row")).toHaveCount(10);
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.locator(".report-index__row")).toHaveCount(0);
  await expect(page.getByText("Page 2")).toHaveCount(0);
  failLaterPage = false;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("Page 2")).toBeVisible();
  await expect(page.locator(".report-index__row")).toHaveCount(1);
  expect(requestedOffsets).toEqual([0, 10, 10]);
});

for (const reportCount of [6, 12]) test(`Machine Detail bounds an exact ${reportCount}-report history`, async ({ page }) => {
  await mockApi(page);
  const summaries = Array.from({ length: reportCount }, (_, index) => ({ ...summary, report_id: index === 0 ? report.report_id : `report-${index + 1}` }));
  await page.route(`**/api/machines/${machine.id}/maintenance-reports?**`, async (route) => {
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get("offset"));
    const payload = summaries.slice(offset, offset + Number(url.searchParams.get("limit")));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto(`/machines/${machine.id}`);
  await expect(page.locator(".history-list--timeline > a")).toHaveCount(6);
  if (reportCount === 12) {
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Page 2")).toBeVisible();
    await expect(page.locator(".history-list--timeline > a")).toHaveCount(6);
  }
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();
});

test("Machine Detail resets its page when the route switches to a machine with no history", async ({ page }) => {
  await mockApi(page);
  const machineB = { id: "33333333-3333-4333-8333-333333333333", name: "Compressor South", asset_type: "rotating_equipment" };
  const summaries = Array.from({ length: 7 }, (_, index) => ({ ...summary, report_id: index === 0 ? report.report_id : `report-${index + 1}` }));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    if (path === `/machines/${machineB.id}`) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(machineB) });
      return;
    }
    if (path === `/machines/${machine.id}/maintenance-reports` || path === `/machines/${machineB.id}/maintenance-reports`) {
      const offset = Number(url.searchParams.get("offset"));
      const records = path.includes(machineB.id) ? [] : summaries;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(records.slice(offset, offset + Number(url.searchParams.get("limit")))) });
      return;
    }
    await route.fallback();
  });
  await page.goto(`/machines/${machine.id}`);
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Page 2")).toBeVisible();
  await page.evaluate((id) => {
    window.history.pushState({}, "", `/machines/${id}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, machineB.id);
  await expect(page.getByRole("heading", { name: machineB.name })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No reports yet" })).toBeVisible();
  await expect(page.getByText("Page 2")).toHaveCount(0);
});

test("malformed successful machine response shows a safe retry state instead of a blank page", async ({ page }) => {
  let malformed = true;
  const problems = captureConsole(page);
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    const payload = path === "/machines" ? (malformed ? { machines: [machine] } : [machine]) : { status: "ok" };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/machines");
  await expect(page.getByRole("alert")).toContainText("SentinelAI returned an invalid response. Retry the request.");
  await expect(page.getByRole("heading", { name: "Stored Machines" })).toBeVisible();
  expect(problems.filter((item) => item.startsWith("pageerror:"))).toEqual([]);
  malformed = false;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("heading", { name: machine.name })).toBeVisible();
});

test("Run Analysis keeps keyboard focus inside the dialog and restores its trigger", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/machines/${machine.id}`);
  const trigger = page.getByRole("button", { name: "Run Analysis" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Run Analysis" });
  await expect(dialog).toBeVisible();
  await expect(page.locator("#root")).toHaveJSProperty("inert", true);
  await expect(page.getByRole("button", { name: "Close", exact: true })).toBeFocused();
  await page.locator("#root a").first().evaluate((element) => (element as HTMLElement).focus());
  await expect(page.getByRole("button", { name: "Close", exact: true })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Create verified report" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Close", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(page.locator("#root")).toHaveJSProperty("inert", false);
  await page.keyboard.press("Enter");
  await expect(dialog).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("Run Analysis restores a sensible focus target when submission navigates away", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/machines/${machine.id}`);
  await page.getByRole("button", { name: "Run Analysis" }).click();
  await page.getByRole("textbox", { name: /Time-series samples/ }).fill(JSON.stringify([
    { ch1_bias: 1, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
    { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
  ]));
  await page.getByRole("button", { name: "Create verified report" }).click();
  await expect(page).toHaveURL(new RegExp(`/reports/${report.report_id}$`));
  await expect(page.locator('.nav-link[aria-current="page"]')).toBeFocused();
});

test("malformed successful creation replays the exact request before navigating", async ({ page }) => {
  await mockApi(page);
  const problems = captureConsole(page);
  const requests: { key: string | null; payload: string | null }[] = [];
  await page.route(`**/api/machines/${machine.id}/maintenance-reports/timeseries`, async (route) => {
    const request = route.request();
    requests.push({ key: request.headers()["idempotency-key"] ?? null, payload: request.postData() });
    await route.fulfill({
      status: requests.length === 1 ? 201 : 200,
      contentType: "application/json",
      body: JSON.stringify(requests.length === 1 ? { report_id: report.report_id } : report),
    });
  });

  await page.goto(`/machines/${machine.id}`);
  await page.getByRole("button", { name: "Run Analysis" }).click();
  const samples = page.getByRole("textbox", { name: /Time-series samples/ });
  await samples.fill(JSON.stringify([
    { ch1_bias: 1, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
    { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
  ]));
  await page.getByRole("button", { name: "Create verified report" }).click();
  await expect(page.getByRole("alert")).toContainText("outcome could not be confirmed");
  await expect(samples).toBeDisabled();
  await page.getByRole("button", { name: "Retry exact request" }).click();
  await expect(page).toHaveURL(new RegExp(`/reports/${report.report_id}$`));
  await expect(page.getByRole("heading", { name: "Evidence Package" })).toBeVisible();
  await expect(page.locator('.nav-link[aria-current="page"]')).toBeFocused();
  expect(requests).toHaveLength(2);
  expect(requests[0]?.key).toBeTruthy();
  expect(requests[1]).toEqual(requests[0]);
  expect(problems).toEqual([]);
});

test("valid insufficient-evidence history and creation responses render without an uncertain-write warning", async ({ page }) => {
  await mockApi(page);
  const problems = captureConsole(page);
  const insufficientReport = {
    ...report,
    analysis: { ...report.analysis, condition: "indeterminate", status: "insufficient_evidence", findings: [], health_score: null, risk_level: null,
      claim_support: { condition_available: false, failure_probability_available: false, fault_severity_available: false,
        health_score_available: false, operational_risk_available: false } },
    producing_models: [],
    narrative: { ...report.narrative, finding_explanations: [], inspection_considerations: [] },
  };
  const insufficientEvidence = { ...evidence, sources: [] };
  await page.route(`**/api/maintenance-reports/${report.report_id}`, (route) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(insufficientReport),
  }));
  await page.route(`**/api/maintenance-reports/${report.report_id}/evidence`, (route) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(insufficientEvidence),
  }));
  await page.route(`**/api/machines/${machine.id}/maintenance-reports/timeseries`, (route) => route.fulfill({
    status: 201, contentType: "application/json", body: JSON.stringify(insufficientReport),
  }));

  await page.goto(`/reports/${report.report_id}`);
  await expect(page.getByRole("heading", { name: "Evidence Chain" })).toBeVisible();
  await expect(page.getByText("Source metadata was not returned")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.goto(`/machines/${machine.id}`);
  await page.getByRole("button", { name: "Run Analysis" }).click();
  await page.getByRole("textbox", { name: /Time-series samples/ }).fill(JSON.stringify([
    { ch1_bias: 1, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
    { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
  ]));
  await page.getByRole("button", { name: "Create verified report" }).click();
  await expect(page).toHaveURL(new RegExp(`/reports/${report.report_id}$`));
  await expect(page.getByText("outcome could not be confirmed")).toHaveCount(0);
  expect(problems).toEqual([]);
});

test("late successful creation stays with Machine A without redirecting Machine B", async ({ page }) => {
  await mockApi(page);
  const problems = captureConsole(page);
  const machineB = { id: "33333333-3333-4333-8333-333333333333", name: "Compressor South", asset_type: "rotating_equipment" };
  await page.route(`**/api/machines/${machineB.id}**`, (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify(new URL(route.request().url()).pathname.endsWith(machineB.id) ? machineB : []),
  }));
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  await page.route(`**/api/machines/${machine.id}/maintenance-reports/timeseries`, async (route) => {
    await held;
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(report) });
  });

  await page.goto(`/machines/${machine.id}`);
  await page.getByRole("button", { name: "Run Analysis" }).click();
  await page.getByRole("textbox", { name: /Time-series samples/ }).fill(JSON.stringify([
    { ch1_bias: 1, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
    { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
  ]));
  const request = page.waitForRequest((item) => item.method() === "POST" && item.url().includes("/maintenance-reports/timeseries"));
  await page.getByRole("button", { name: "Create verified report" }).click();
  await request;
  await page.evaluate((id) => { window.history.pushState({}, "", `/machines/${id}`); window.dispatchEvent(new PopStateEvent("popstate")); }, machineB.id);
  await expect(page.getByRole("heading", { name: machineB.name })).toBeVisible();
  release();
  await page.getByRole("button", { name: "Run Analysis" }).first().click();
  await expect(page.getByRole("alert")).toContainText("complete");
  await expect(page).toHaveURL(new RegExp(`/machines/${machineB.id}$`));
  await page.getByRole("link", { name: "Return to originating machine" }).click();
  await page.locator(".signature-hero__actions").getByRole("button", { name: "Run Analysis", exact: true }).click();
  await expect(page.getByRole("button", { name: "Open created report" })).toBeVisible();
  await page.getByRole("button", { name: "Open created report" }).click();
  await expect(page).toHaveURL(new RegExp(`/reports/${report.report_id}$`));
  expect(problems).toEqual([]);
});

test("late malformed creation retains the exact request after Machine A to B to A navigation", async ({ page }) => {
  await mockApi(page);
  const problems = captureConsole(page);
  const machineB = { id: "33333333-3333-4333-8333-333333333333", name: "Compressor South", asset_type: "rotating_equipment" };
  await page.route(`**/api/machines/${machineB.id}**`, (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify(new URL(route.request().url()).pathname.endsWith(machineB.id) ? machineB : []),
  }));
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  const requests: { key: string | null; payload: string | null }[] = [];
  await page.route(`**/api/machines/${machine.id}/maintenance-reports/timeseries`, async (route) => {
    requests.push({ key: route.request().headers()["idempotency-key"] ?? null, payload: route.request().postData() });
    if (requests.length === 1) await held;
    await route.fulfill({ status: requests.length === 1 ? 201 : 200, contentType: "application/json",
      body: JSON.stringify(requests.length === 1 ? { report_id: report.report_id } : report) });
  });

  await page.goto(`/machines/${machine.id}`);
  await page.getByRole("button", { name: "Run Analysis" }).click();
  await page.getByRole("textbox", { name: /Time-series samples/ }).fill(JSON.stringify([
    { ch1_bias: 1, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
    { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
  ]));
  const request = page.waitForRequest((item) => item.method() === "POST" && item.url().includes("/maintenance-reports/timeseries"));
  await page.getByRole("button", { name: "Create verified report" }).click();
  await request;
  await page.evaluate((id) => { window.history.pushState({}, "", `/machines/${id}`); window.dispatchEvent(new PopStateEvent("popstate")); }, machineB.id);
  await expect(page.getByRole("heading", { name: machineB.name })).toBeVisible();
  release();
  await page.getByRole("button", { name: "Run Analysis" }).first().click();
  await expect(page.getByRole("alert")).toContainText("unresolved");
  await expect(page.getByRole("button", { name: "Create verified report" })).toHaveCount(0);
  await page.getByRole("link", { name: "Return to originating machine" }).click();
  await page.locator(".signature-hero__actions").getByRole("button", { name: "Run Analysis", exact: true }).click();
  await page.getByRole("button", { name: "Retry exact request" }).click();
  await expect(page).toHaveURL(new RegExp(`/reports/${report.report_id}$`));
  expect(requests).toHaveLength(2);
  expect(requests[0]?.key).toBeTruthy();
  expect(requests[1]).toEqual(requests[0]);
  expect(problems).toEqual([]);
});

test("affected history and dialog surfaces remain usable across review widths", async ({ page }, testInfo) => {
  await mockApi(page);
  let malformedMachines = false;
  await page.route("**/api/machines", async (route) => {
    if (!malformedMachines) return route.fallback();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ machines: [machine] }) });
  });
  const problems = captureConsole(page);
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/reports");
    await expect(page.locator(".report-index__row")).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: testInfo.outputPath(`history-${width}.png`), fullPage: true, animations: "disabled" });

    await page.goto(`/machines/${machine.id}`);
    await page.getByRole("button", { name: "Run Analysis" }).click();
    await page.getByRole("button", { name: "Audio" }).click();
    await expect(page.getByText("WAV audio file only; no live audio acquisition.")).toBeVisible();
    await expect.poll(() => page.getByRole("dialog").evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return rect.left >= 0 && rect.right <= window.innerWidth + 1;
    })).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`analysis-dialog-${width}.png`), animations: "disabled" });
    await page.keyboard.press("Escape");

    malformedMachines = true;
    await page.goto("/machines");
    await expect(page.getByRole("alert")).toContainText("SentinelAI returned an invalid response.");
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: testInfo.outputPath(`invalid-response-${width}.png`), fullPage: true, animations: "disabled" });
    malformedMachines = false;
  }
  expect(problems.filter((item) => item.startsWith("pageerror:"))).toEqual([]);
});
