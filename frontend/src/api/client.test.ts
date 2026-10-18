import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest } from "./client";
import { listMachines } from "./machines";
import { createMaintenanceReport, getMaintenanceReport, getMaintenanceReportEvidence, listMachineReports } from "./reports";
import { evidence, machine, report } from "../test/fixtures";

const insufficientReport = {
  ...report,
  analysis: {
    ...report.analysis,
    condition: "indeterminate",
    status: "insufficient_evidence",
    findings: [],
    health_score: null,
    risk_level: null,
    claim_support: {
      condition_available: false,
      failure_probability_available: false,
      fault_severity_available: false,
      health_score_available: false,
      operational_risk_available: false,
    },
  },
  producing_models: [],
  narrative: { ...report.narrative, finding_explanations: [], inspection_considerations: [] },
};

const insufficientEvidence = { ...evidence, sources: [] };

afterEach(() => vi.unstubAllGlobals());

describe("central API error handling", () => {
  it.each([
    [400, "Unsupported input"],
    [404, "Machine not found"],
    [409, "already processing"],
    [422, "Submitted fields are invalid"],
    [503, "Model unavailable"],
  ])("renders safe backend detail for %s", async (status, detail) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail }), { status, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("/test")).rejects.toMatchObject({ status });
  });

  it("suppresses server filesystem detail", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Model missing at C:\\private\\model.joblib" }), { status: 500, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("/test")).rejects.toEqual(expect.objectContaining({ message: "The server could not safely complete this request." }));
  });

  it("marks network failures as transport uncertain", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    await expect(apiRequest("/test")).rejects.toEqual(expect.objectContaining({ status: 0, transportUncertain: true }));
  });

  it.each([
    { machines: [] },
    null,
    [{ id: "machine-1", name: "Pump" }],
    [{ id: "machine-1", name: 7, asset_type: "pump" }],
  ])("rejects malformed successful machine collections without treating them as empty", async (payload) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })));
    await expect(listMachines()).rejects.toMatchObject({
      message: "SentinelAI returned an invalid response. Retry the request.",
    });
  });

  it("keeps validation detail available to developers without exposing it in the UI message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([{ id: "machine-1", name: "Pump" }]), { status: 200 })));
    const error = await listMachines().catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).not.toContain("asset_type");
    expect((error as ApiError).cause).toBeInstanceOf(Error);
    expect(((error as ApiError).cause as Error).message).toContain("asset_type");
  });

  it("accepts a valid empty collection but rejects malformed JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));
    await expect(listMachines()).resolves.toEqual([]);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[", { status: 200 })));
    await expect(listMachines()).rejects.toMatchObject({ message: "SentinelAI returned an invalid response. Retry the request." });
  });

  it("rejects report-list and evidence array/object mismatches at the API boundary", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ reports: [] }), { status: 200 })));
    await expect(listMachineReports("machine-1")).rejects.toBeInstanceOf(ApiError);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })));
    await expect(getMaintenanceReportEvidence("report-1")).rejects.toBeInstanceOf(ApiError);
  });

  it("accepts backend-valid empty findings, producing models, and evidence sources", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(insufficientReport), { status: 200 })));
    await expect(getMaintenanceReport(report.report_id)).resolves.toEqual(insufficientReport);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(insufficientEvidence), { status: 200 })));
    await expect(getMaintenanceReportEvidence(report.report_id)).resolves.toEqual(insufficientEvidence);
  });

  it.each([
    ["findings", { ...report, analysis: { ...report.analysis, findings: [] } }],
    ["producing models", { ...report, producing_models: [] }],
  ])("accepts otherwise valid reports with empty %s", async (_label, payload) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })));
    await expect(getMaintenanceReport(report.report_id)).resolves.toEqual(payload);
  });

  it("accepts a valid insufficient-evidence POST as confirmed success", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(insufficientReport), { status: 201 })));
    await expect(createMaintenanceReport(machine.id, {
      modality: "timeseries",
      samples: [
        { ch1_bias: 1, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
        { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
      ],
      intent: "summarize_analysis",
    }, "insufficient-request")).resolves.toEqual(insufficientReport);
  });

  it("still rejects invalid roots, array members, and missing required report fields", async () => {
    for (const payload of [null, { ...insufficientReport, analysis: { ...insufficientReport.analysis, findings: "none" } },
      { ...insufficientReport, analysis: { ...insufficientReport.analysis, findings: [null] } },
      { ...insufficientReport, producing_models: [{}] }, { ...insufficientReport, producing_models: undefined }]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })));
      await expect(getMaintenanceReport(report.report_id)).rejects.toBeInstanceOf(ApiError);
    }
    for (const payload of [{ ...insufficientEvidence, sources: {} }, { ...insufficientEvidence, sources: [{}] },
      { ...insufficientEvidence, sources: undefined }]) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })));
      await expect(getMaintenanceReportEvidence(report.report_id)).rejects.toBeInstanceOf(ApiError);
    }
  });
});
