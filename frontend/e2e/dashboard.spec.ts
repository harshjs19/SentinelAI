import { expect, test, type ConsoleMessage, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

interface DemoSnapshotData {
  machines: { id: string; name: string; asset_type: string }[];
  reports_by_machine: Record<string, unknown[]>;
  evidence: Record<string, {
    sources: { sha256: string }[];
    analysis: { analysis_id: string };
    evidence_package: { package_digest_sha256: string };
    retrieval_bundle: { corpus_digest_sha256: string };
    report: { report_digest_sha256: string };
  }>;
  reports: Record<string, {
    report_id: string;
    machine_id: string;
    generated_at: string;
    analysis: { condition: string };
    producing_models: { model_id: string }[];
  }>;
  capabilities: { models: { model_id: string }[] };
}

interface EvaluationIndexData {
  models: {
    metric_label: string;
    metric_value: number;
    known_limitation: string;
  }[];
}

const snapshot = JSON.parse(
  readFileSync(new URL("../public/demo/snapshot.json", import.meta.url), "utf8"),
) as DemoSnapshotData;
const evaluations = JSON.parse(
  readFileSync(new URL("../public/model-evaluations.json", import.meta.url), "utf8"),
) as EvaluationIndexData;

const machines = snapshot.machines;
const reports = Object.values(snapshot.reports).sort(
  (left, right) => Date.parse(right.generated_at) - Date.parse(left.generated_at),
);
const latestReport = reports[0]!;
const latestMachine = machines.find((machine) => machine.id === latestReport.machine_id)!;

function isKnownBrowserDriverNoise(message: ConsoleMessage) {
  const text = message.text();
  return message.type() === "warning" && text.includes("GL Driver Message") && text.includes("GPU stall due to ReadPixels");
}

function monitorPage(page: Page) {
  const consoleProblems: string[] = [];
  const requestFailures: string[] = [];
  const errorResponses: string[] = [];
  const apiRequests: string[] = [];
  page.on("console", (message) => {
    if ((message.type() === "error" || message.type() === "warning") && !isKnownBrowserDriverNoise(message)) {
      consoleProblems.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => consoleProblems.push(`pageerror: ${error.message}`));
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) apiRequests.push(request.url());
  });
  page.on("requestfailed", (request) => requestFailures.push(`${request.method()} ${request.url()}`));
  page.on("response", (response) => {
    if (response.status() >= 400) errorResponses.push(`${response.status()} ${response.url()}`);
  });
  return { consoleProblems, requestFailures, errorResponses, apiRequests };
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect.poll(() => page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  )).toBe(true);
}

async function expectSemanticIntegrity(page: Page) {
  const text = await page.locator("body").innerText();
  for (const marker of ["undefined", "null", "NaN", "Infinity", "[object Object]", "Coming soon", "Invalid Date"]) {
    expect(text, `rendered marker ${marker}`).not.toContain(marker);
  }
  expect(text).not.toMatch(/(^|\s)N\/A($|\s)/m);
  expect(text.split("\n").map((line) => line.trim())).not.toContain("—");
  for (const match of text.matchAll(/(-?\d+(?:\.\d+)?)%/g)) {
    const value = Number(match[1]);
    expect(Number.isFinite(value)).toBe(true);
    expect(value).toBeGreaterThanOrEqual(0);
    expect(value).toBeLessThanOrEqual(100);
  }
}

async function revealEvidenceNodes(page: Page) {
  const nodes = page.locator(".evidence-node");
  await expect(nodes).toHaveCount(5);
  for (let index = 0; index < await nodes.count(); index += 1) {
    await nodes.nth(index).scrollIntoViewIfNeeded();
    await expect(nodes.nth(index)).toHaveCSS("opacity", "1");
  }
  await page.evaluate(() => window.scrollTo(0, 0));
}

async function expectHealthyDemo(monitor: ReturnType<typeof monitorPage>) {
  expect(monitor.consoleProblems).toEqual([]);
  expect(monitor.requestFailures).toEqual([]);
  expect(monitor.errorResponses).toEqual([]);
  expect(monitor.apiRequests).toEqual([]);
}

test("Evidence Chain keeps all five stored stages readable from 320px through desktop", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const monitor = monitorPage(page);
  const expectedLabels = ["Source", "Analysis", "Evidence Package", "Retrieval Bundle", "Maintenance Report"];
  const storedEvidence = snapshot.evidence[latestReport.report_id]!;

  for (const width of [320, 375, 390, 430, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/reports/${latestReport.report_id}`);
    await revealEvidenceNodes(page);
    const chain = page.locator(".evidence-chain");
    const nodes = chain.locator(".evidence-node");
    expect(await nodes.locator(":scope > small").allTextContents()).toEqual(expectedLabels);
    await expectNoHorizontalOverflow(page);
    const layout = await chain.evaluate((element) => {
      const cards = Array.from(element.querySelectorAll<HTMLElement>(".evidence-node"));
      const heading = element.querySelector(".section-heading")!.getBoundingClientRect();
      const track = element.querySelector(".evidence-chain__track")!.getBoundingClientRect();
      return {
        headingClear: heading.bottom <= track.top + 1,
        cardOverlap: cards.slice(0, -1).some((card, index) => card.getBoundingClientRect().bottom > cards[index + 1]!.getBoundingClientRect().top + 1),
        clippedLabels: cards.some((card) => {
          const label = card.querySelector<HTMLElement>(":scope > small")!;
          return label.scrollWidth > label.clientWidth + 1 || label.scrollHeight > label.clientHeight + 1;
        }),
        minValueWidth: Math.min(...cards.map((card) => card.querySelector("strong")!.getBoundingClientRect().width)),
        architectureVisible: getComputedStyle(element.querySelector(".evidence-chain__architecture")!).display !== "none",
      };
    });
    expect(layout.headingClear).toBe(true);
    if (width <= 900) expect(layout.cardOverlap).toBe(false);
    expect(layout.clippedLabels).toBe(false);
    if (width <= 900) {
      expect(layout.minValueWidth).toBeGreaterThan(120);
      expect(layout.architectureVisible).toBe(false);
    }
    await chain.screenshot({ path: testInfo.outputPath(`evidence-chain-${width}.png`), animations: "disabled" });
  }

  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto(`/reports/${latestReport.report_id}`);
  const nodes = page.locator(".evidence-chain .evidence-node");
  const fullDetails = [
    storedEvidence.sources[0]!.sha256,
    storedEvidence.analysis.analysis_id,
    storedEvidence.evidence_package.package_digest_sha256,
    storedEvidence.retrieval_bundle.corpus_digest_sha256,
    storedEvidence.report.report_digest_sha256,
  ];
  for (let index = 0; index < fullDetails.length; index += 1) {
    await expect(nodes.nth(index).locator(".evidence-node__detail code")).toHaveText(fullDetails[index]!);
  }
  await nodes.first().focus();
  await page.keyboard.press("Tab");
  await expect(nodes.nth(1)).toBeFocused();
  await expect(nodes.nth(1).locator(".evidence-node__detail")).toHaveCSS("opacity", "1");
  await expect(page.getByText(latestReport.producing_models[0]!.model_id).first()).toBeVisible();

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/reports/${latestReport.report_id}`);
  await expect(page.locator(".evidence-chain__signal--vertical")).toHaveCSS("display", "none");
  await revealEvidenceNodes(page);
  await expectHealthyDemo(monitor);
});

test("public demo tells the complete stored-evidence story without invented values", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const monitor = monitorPage(page);

  await page.goto("/");
  await expect(page.getByText("PUBLIC DEMO · READ ONLY", { exact: true })).toBeVisible();
  await expect(page.getByText("Demonstration records generated through SentinelAI's simulation/replay workflow.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Stored machine analyses with verifiable provenance/i })).toBeVisible();
  await expect(page.locator(".metric-card", { hasText: "Demo machines" }).locator("strong")).toHaveText(String(machines.length));
  await expect(page.locator(".metric-card", { hasText: "Stored reports" }).locator("strong")).toHaveText(String(reports.length));
  const conditions = page.locator(".condition-counts").getByRole("definition");
  await expect(conditions).toHaveCount(3);
  await expect(page.locator(".condition-counts")).toContainText("Normal0");
  await expect(page.locator(".condition-counts")).toContainText(`Abnormal${reports.length}`);
  await expect(page.locator(".condition-counts")).toContainText("Indeterminate0");
  await expect(page.locator(".recent-analysis")).toContainText(latestMachine.name);
  await expect(page.locator(".recent-analysis")).toContainText(latestReport.producing_models[0]!.model_id);
  await expect(page.getByRole("heading", { name: "Model lifecycle" })).toBeVisible();
  await expectSemanticIntegrity(page);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("overview-1440.png"), fullPage: true });

  await page.getByRole("link", { name: "Machines", exact: true }).click();
  for (const machine of machines) await expect(page.getByRole("heading", { name: machine.name })).toBeVisible();
  await expect(page.locator(".machine-card")).toHaveCount(machines.length);
  await expectSemanticIntegrity(page);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("machines-1440.png"), fullPage: true });

  await page.goto(`/machines/${latestMachine.id}`);
  await expect(page.getByRole("heading", { name: latestMachine.name })).toBeVisible();
  await expect(page.getByRole("button", { name: /Analysis disabled in public demo/ })).toBeDisabled();
  await expect(page.getByRole("heading", { name: "Evidence Chain" })).toBeVisible();
  await expect(page.getByText("Raw / uncalibrated classifier confidence")).toBeVisible();
  await expect(page.getByText(/Not failure probability, fault severity, machine health/i)).toBeVisible();
  await expectSemanticIntegrity(page);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("machine-detail-1440.png"), fullPage: true });

  await page.getByRole("link", { name: "Maintenance Reports" }).click();
  await expect(page.getByRole("heading", { name: /Maintenance History/i })).toBeVisible();
  const firstMachineReports = Object.values(snapshot.reports_by_machine)[0]!;
  await expect(page.locator(".report-index__row")).toHaveCount(firstMachineReports.length);
  const timeline = page.getByRole("region", { name: "Stored maintenance report timeline" });
  await timeline.scrollIntoViewIfNeeded();
  await expect(timeline).toBeVisible();
  await expect(page.locator(".report-index__row").first()).toBeVisible();
  await expect(page.getByText("Report generated", { exact: true }).first()).toBeVisible();
  await expectSemanticIntegrity(page);
  await expectNoHorizontalOverflow(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("history-1440.png"), fullPage: true });

  await page.goto(`/reports/${latestReport.report_id}`);
  await expect(page.getByRole("heading", { name: "Evidence Chain" })).toBeVisible();
  await revealEvidenceNodes(page);
  await expect(page.getByRole("heading", { name: "Evidence Package" })).toBeVisible();
  await expect(page.getByText("Analysis created", { exact: true })).toBeVisible();
  await expect(page.getByText("Evidence Package created", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Report generated", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(latestReport.producing_models[0]!.model_id).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Inspection Considerations" })).toBeVisible();
  await expect(page.getByText(/they are not commands, urgency ratings, or authorization/i)).toBeVisible();
  await expectSemanticIntegrity(page);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("report-evidence-1440.png"), fullPage: true });

  await page.getByRole("link", { name: "Model Capabilities" }).click();
  await expect(page.getByRole("heading", { name: /Model Capabilities/i })).toBeVisible();
  await expect(page.locator(".capability-card")).toHaveCount(snapshot.capabilities.models.length);
  for (const evaluation of evaluations.models) {
    await expect(page.getByText(evaluation.metric_label, { exact: true })).toBeVisible();
    await expect(page.getByText(`${(evaluation.metric_value * 100).toFixed(1)}%`, { exact: true })).toBeVisible();
    await expect(page.getByText(evaluation.known_limitation, { exact: true })).toBeVisible();
  }
  await expect(page.getByText("Rejected Experiment", { exact: true })).toBeVisible();
  await expect(page.getByText("Experimental", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: /audio_mimii_ast_v2/i }).click();
  await expect(page.getByText(/Preserved as a rejected experimental result/i)).toBeVisible();
  await expectSemanticIntegrity(page);
  await expectNoHorizontalOverflow(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("models-1440.png"), fullPage: true });

  await expectHealthyDemo(monitor);
});

test("public demo history selection preserves report and evidence navigation without API calls", async ({ page }) => {
  const monitor = monitorPage(page);
  const first = machines[0]!;
  const second = machines[1]!;
  const firstReports = snapshot.reports_by_machine[first.id]!;
  const secondReports = snapshot.reports_by_machine[second.id]!;
  const secondReportId = (secondReports[0] as { report_id: string }).report_id;

  await page.goto("/reports");
  await expect(page.getByText("PUBLIC DEMO · READ ONLY", { exact: true })).toBeVisible();
  await expect(page.locator(".report-index__row")).toHaveCount(firstReports.length);
  await page.getByLabel("Machine history").selectOption(second.id);
  await expect(page.locator(".report-index__row")).toHaveCount(secondReports.length);
  await expect(page.locator(".report-index__row").first()).toHaveAttribute("href", `/reports/${secondReportId}`);
  await page.locator(".report-index__row").first().click();
  await expect(page).toHaveURL(new RegExp(`/reports/${secondReportId}$`));
  await expect(page.getByRole("heading", { name: "Evidence Package" })).toBeVisible();
  await page.getByRole("link", { name: "Model Capabilities" }).click();
  await expect(page.locator(".capability-card")).toHaveCount(snapshot.capabilities.models.length);
  await expectHealthyDemo(monitor);
});

test("1280 and tablet layouts preserve meaning, reduced motion, and WebGL fallback", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const monitor = monitorPage(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`/reports/${latestReport.report_id}`);
  await expect(page.getByRole("heading", { name: "Evidence Chain" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expectSemanticIntegrity(page);
  await page.screenshot({ path: testInfo.outputPath("report-1280.png"), fullPage: true });

  await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto(`/reports/${latestReport.report_id}`);
  await revealEvidenceNodes(page);
  await expectNoHorizontalOverflow(page);
  await expectSemanticIntegrity(page);
  await page.screenshot({ path: testInfo.outputPath("report-evidence-1024.png"), fullPage: true });

  await page.setViewportSize({ width: 768, height: 1024 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (contextId: string, ...args: unknown[]) {
      if (contextId === "webgl" || contextId === "experimental-webgl" || contextId === "webgl2") return null;
      return original.call(this, contextId as never, ...(args as []));
    } as typeof HTMLCanvasElement.prototype.getContext;
  });
  await page.goto("/");
  await expect(page.locator(".static-core:not(.static-core--loading)")).toBeVisible();
  const animationDuration = await page.locator(".ambient-canvas__glow").first().evaluate((element) => getComputedStyle(element).animationDuration);
  const durationMs = animationDuration.endsWith("ms") ? Number.parseFloat(animationDuration) : Number.parseFloat(animationDuration) * 1000;
  expect(durationMs).toBeLessThanOrEqual(0.001);
  await expectNoHorizontalOverflow(page);
  await expectSemanticIntegrity(page);
  await page.screenshot({ path: testInfo.outputPath("overview-tablet-fallback.png"), fullPage: true });

  for (const route of ["/machines", `/machines/${latestMachine.id}`, "/reports", `/reports/${latestReport.report_id}`, "/models"]) {
    await page.goto(route);
    await expect(page.getByText("PUBLIC DEMO · READ ONLY", { exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await expectSemanticIntegrity(page);
  }
  await expect(page.getByText("Rejected Experiment", { exact: true })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Stored machine analyses with verifiable provenance/i })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expectSemanticIntegrity(page);
  await page.screenshot({ path: testInfo.outputPath("overview-mobile-390.png"), fullPage: true });

  await page.goto(`/reports/${latestReport.report_id}`);
  await revealEvidenceNodes(page);
  await expectNoHorizontalOverflow(page);
  await expectSemanticIntegrity(page);
  await page.screenshot({ path: testInfo.outputPath("report-mobile-390.png"), fullPage: true });
  await expectHealthyDemo(monitor);
});

test("malformed public snapshot fails safely without exposing parser details", async ({ page }) => {
  await page.route("**/demo/snapshot.json", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: "{\"schema_version\":",
  }));
  const monitor = monitorPage(page);
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Public demonstration records could not be loaded.");
  await expect(page.getByRole("alert")).not.toContainText(/JSON|snapshot\.json|Unexpected end|SyntaxError/i);
  expect(monitor.apiRequests).toEqual([]);
  expect(monitor.consoleProblems).toEqual([]);
});

test("malformed model evaluation index fails safely", async ({ page }) => {
  await page.route("**/model-evaluations.json", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: "{\"schema_version\":\"invalid\"}",
  }));
  const monitor = monitorPage(page);
  await page.goto("/models");
  await expect(page.getByRole("alert")).toContainText("Verified model evaluation summaries could not be loaded.");
  await expect(page.getByRole("alert")).not.toContainText(/schema|model-evaluations\.json|parse/i);
  expect(monitor.apiRequests).toEqual([]);
  expect(monitor.consoleProblems).toEqual([]);
});
