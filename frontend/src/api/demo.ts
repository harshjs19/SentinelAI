import { ApiError } from "./client";
import type {
  MaintenanceReport,
  MaintenanceReportEvidence,
  MaintenanceReportSummary,
  Machine,
  ModelCapabilitiesResponse,
} from "./types";

export const PUBLIC_DEMO =
  import.meta.env.MODE === "demo" || import.meta.env.VITE_PUBLIC_DEMO === "true";

interface DemoSnapshot {
  schema_version: string;
  exported_at: string;
  environment: "PUBLIC DEMO";
  read_only: true;
  provenance: string;
  machines: Machine[];
  capabilities: ModelCapabilitiesResponse;
  reports_by_machine: Record<string, MaintenanceReportSummary[]>;
  reports: Record<string, MaintenanceReport>;
  evidence: Record<string, MaintenanceReportEvidence>;
}

type JsonRecord = Record<string, unknown>;

function record(value: unknown, path: string): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${path} must be an object`);
  }
  return value as JsonRecord;
}

function array(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${path} must be an array`);
  return value;
}

function text(value: unknown, path: string): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${path} must be a non-empty string`);
  }
  return value;
}

function timestamp(value: unknown, path: string): string {
  const result = text(value, path);
  if (!Number.isFinite(Date.parse(result))) throw new Error(`${path} must be a valid timestamp`);
  return result;
}

function number(value: unknown, path: string, minimum = Number.NEGATIVE_INFINITY): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum) {
    throw new Error(`${path} must be a finite number`);
  }
  return value;
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${path} must be a boolean`);
  return value;
}

function stringArray(value: unknown, path: string): string[] {
  return array(value, path).map((item, index) => text(item, `${path}[${index}]`));
}

function validateMachine(value: unknown, path: string): void {
  const item = record(value, path);
  text(item.id, `${path}.id`);
  text(item.name, `${path}.name`);
  text(item.asset_type, `${path}.asset_type`);
}

function validateCapability(value: unknown, path: string): void {
  const item = record(value, path);
  text(item.model_id, `${path}.model_id`);
  text(item.modality, `${path}.modality`);
  text(item.status, `${path}.status`);
  boolean(item.runtime_default, `${path}.runtime_default`);
  text(item.validated_scope, `${path}.validated_scope`);
  text(item.evaluation_reference, `${path}.evaluation_reference`);
  text(item.confidence_semantics, `${path}.confidence_semantics`);
}

function validateSummary(value: unknown, path: string): void {
  const item = record(value, path);
  text(item.report_id, `${path}.report_id`);
  text(item.machine_id, `${path}.machine_id`);
  timestamp(item.generated_at, `${path}.generated_at`);
  text(item.generation_status, `${path}.generation_status`);
  text(item.condition, `${path}.condition`);
  text(item.analysis_status, `${path}.analysis_status`);
  text(item.executive_summary, `${path}.executive_summary`);
}

function validateNarrativeItem(value: unknown, path: string): void {
  const item = record(value, path);
  text(item.finding_id, `${path}.finding_id`);
  text(item.text, `${path}.text`);
  stringArray(item.citation_ids, `${path}.citation_ids`);
}

function validateReport(value: unknown, path: string): void {
  const item = record(value, path);
  text(item.report_id, `${path}.report_id`);
  text(item.machine_id, `${path}.machine_id`);
  timestamp(item.generated_at, `${path}.generated_at`);
  text(item.generation_status, `${path}.generation_status`);
  text(item.request_disposition, `${path}.request_disposition`);
  text(item.request_intent, `${path}.request_intent`);
  text(item.disclaimer, `${path}.disclaimer`);

  const analysis = record(item.analysis, `${path}.analysis`);
  text(analysis.condition, `${path}.analysis.condition`);
  text(analysis.status, `${path}.analysis.status`);
  const findings = array(analysis.findings, `${path}.analysis.findings`);
  if (findings.length === 0) throw new Error(`${path}.analysis.findings cannot be empty`);
  findings.forEach((value, index) => {
    const finding = record(value, `${path}.analysis.findings[${index}]`);
    text(finding.finding_id, `${path}.analysis.findings[${index}].finding_id`);
    text(finding.modality, `${path}.analysis.findings[${index}].modality`);
    text(finding.code, `${path}.analysis.findings[${index}].code`);
    text(finding.condition, `${path}.analysis.findings[${index}].condition`);
    const confidence = number(
      finding.confidence,
      `${path}.analysis.findings[${index}].confidence`,
      0,
    );
    if (confidence > 1) throw new Error(`${path}.analysis.findings confidence exceeds 1`);
    text(finding.confidence_kind, `${path}.analysis.findings[${index}].confidence_kind`);
  });
  const support = record(analysis.claim_support, `${path}.analysis.claim_support`);
  [
    "condition_available",
    "failure_probability_available",
    "fault_severity_available",
    "health_score_available",
    "operational_risk_available",
  ].forEach((key) => boolean(support[key], `${path}.analysis.claim_support.${key}`));

  const narrative = record(item.narrative, `${path}.narrative`);
  text(narrative.executive_summary, `${path}.narrative.executive_summary`);
  array(narrative.finding_explanations, `${path}.narrative.finding_explanations`).forEach(
    (value, index) => validateNarrativeItem(value, `${path}.narrative.finding_explanations[${index}]`),
  );
  array(narrative.inspection_considerations, `${path}.narrative.inspection_considerations`).forEach(
    (value, index) => validateNarrativeItem(value, `${path}.narrative.inspection_considerations[${index}]`),
  );
  if (narrative.knowledge_gap_statement !== null) {
    text(narrative.knowledge_gap_statement, `${path}.narrative.knowledge_gap_statement`);
  }

  const limitations = record(item.limitations, `${path}.limitations`);
  [
    "analysis_limitations",
    "model_scope_limitations",
    "unavailable_claims",
    "generation_limitations",
  ].forEach((key) => stringArray(limitations[key], `${path}.limitations.${key}`));

  array(item.citations, `${path}.citations`).forEach((value, index) => {
    const citation = record(value, `${path}.citations[${index}]`);
    [
      "citation_id",
      "title",
      "publisher",
      "section",
      "fault_code",
      "asset_type",
      "matched_intent",
      "source_lane",
    ].forEach((key) => text(citation[key], `${path}.citations[${index}].${key}`));
  });

  const models = array(item.producing_models, `${path}.producing_models`);
  if (models.length === 0) throw new Error(`${path}.producing_models cannot be empty`);
  models.forEach((value, index) => {
    const model = record(value, `${path}.producing_models[${index}]`);
    ["model_id", "modality", "status", "validated_scope", "confidence_semantics"].forEach(
      (key) => text(model[key], `${path}.producing_models[${index}].${key}`),
    );
    boolean(
      model.runtime_default_at_execution,
      `${path}.producing_models[${index}].runtime_default_at_execution`,
    );
  });

  const safety = record(item.safety_validation, `${path}.safety_validation`);
  boolean(safety.valid, `${path}.safety_validation.valid`);
  text(safety.validator_policy_version, `${path}.safety_validation.validator_policy_version`);
  boolean(safety.repair_attempted, `${path}.safety_validation.repair_attempted`);
  stringArray(safety.violation_codes, `${path}.safety_validation.violation_codes`);
}

function validateEvidence(value: unknown, path: string): void {
  const item = record(value, path);
  const report = record(item.report, `${path}.report`);
  [
    "report_id",
    "report_digest_sha256",
    "schema_version",
    "generation_status",
    "evidence_package_id",
    "evidence_package_digest_sha256",
    "retrieval_bundle_digest_sha256",
  ].forEach((key) => text(report[key], `${path}.report.${key}`));
  timestamp(report.generated_at, `${path}.report.generated_at`);

  const analysis = record(item.analysis, `${path}.analysis`);
  ["analysis_id", "machine_id", "condition", "status"].forEach((key) =>
    text(analysis[key], `${path}.analysis.${key}`),
  );
  timestamp(analysis.created_at, `${path}.analysis.created_at`);

  const evidencePackage = record(item.evidence_package, `${path}.evidence_package`);
  ["package_id", "package_digest_sha256", "schema_version", "analysis_id"].forEach((key) =>
    text(evidencePackage[key], `${path}.evidence_package.${key}`),
  );
  timestamp(evidencePackage.created_at, `${path}.evidence_package.created_at`);

  const retrieval = record(item.retrieval_bundle, `${path}.retrieval_bundle`);
  [
    "retrieval_bundle_digest_sha256",
    "evidence_package_id",
    "evidence_package_digest_sha256",
    "corpus_digest_sha256",
    "embedding_model_id",
    "embedding_model_revision",
    "schema_version",
  ].forEach((key) => text(retrieval[key], `${path}.retrieval_bundle.${key}`));

  const sources = array(item.sources, `${path}.sources`);
  if (sources.length === 0) throw new Error(`${path}.sources cannot be empty`);
  sources.forEach((value, index) => {
    const source = record(value, `${path}.sources[${index}]`);
    ["modality", "source_kind", "sha256", "content_type"].forEach((key) =>
      text(source[key], `${path}.sources[${index}].${key}`),
    );
    number(source.size_bytes, `${path}.sources[${index}].size_bytes`, 0);
  });
}

export function validateDemoSnapshot(value: unknown): DemoSnapshot {
  const snapshot = record(value, "snapshot");
  if (text(snapshot.schema_version, "snapshot.schema_version") !== "1") {
    throw new Error("Unsupported demo snapshot schema");
  }
  timestamp(snapshot.exported_at, "snapshot.exported_at");
  if (snapshot.environment !== "PUBLIC DEMO" || snapshot.read_only !== true) {
    throw new Error("Demo snapshot mode is invalid");
  }
  text(snapshot.provenance, "snapshot.provenance");

  const machines = array(snapshot.machines, "snapshot.machines");
  const machineIds = new Set<string>();
  machines.forEach((value, index) => {
    validateMachine(value, `snapshot.machines[${index}]`);
    machineIds.add(record(value, `snapshot.machines[${index}]`).id as string);
  });
  if (machineIds.size !== machines.length) throw new Error("Demo machine IDs must be unique");

  const capabilities = record(snapshot.capabilities, "snapshot.capabilities");
  const models = array(capabilities.models, "snapshot.capabilities.models");
  if (models.length === 0) throw new Error("Demo capabilities cannot be empty");
  models.forEach((value, index) =>
    validateCapability(value, `snapshot.capabilities.models[${index}]`),
  );

  const reportsByMachine = record(snapshot.reports_by_machine, "snapshot.reports_by_machine");
  const reports = record(snapshot.reports, "snapshot.reports");
  const evidence = record(snapshot.evidence, "snapshot.evidence");
  for (const machineId of machineIds) {
    const summaries = array(
      reportsByMachine[machineId],
      `snapshot.reports_by_machine.${machineId}`,
    );
    summaries.forEach((value, index) => {
      validateSummary(value, `snapshot.reports_by_machine.${machineId}[${index}]`);
      const summary = record(value, `snapshot.reports_by_machine.${machineId}[${index}]`);
      const reportId = summary.report_id as string;
      if (summary.machine_id !== machineId || !reports[reportId] || !evidence[reportId]) {
        throw new Error("Demo report bindings are incomplete");
      }
    });
  }
  for (const [reportId, report] of Object.entries(reports)) {
    validateReport(report, `snapshot.reports.${reportId}`);
    validateEvidence(evidence[reportId], `snapshot.evidence.${reportId}`);
    if (record(report, `snapshot.reports.${reportId}`).report_id !== reportId) {
      throw new Error("Demo report key does not match report ID");
    }
  }
  if (Object.keys(reports).length === 0 || Object.keys(reports).length !== Object.keys(evidence).length) {
    throw new Error("Demo reports and evidence must be non-empty and one-to-one");
  }
  return snapshot as unknown as DemoSnapshot;
}

let snapshotPromise: Promise<DemoSnapshot> | null = null;

export function loadDemoSnapshot(): Promise<DemoSnapshot> {
  if (!snapshotPromise) {
    const url = `${import.meta.env.BASE_URL}demo/snapshot.json`;
    snapshotPromise = fetch(url, { headers: { Accept: "application/json" } })
      .then(async (response) => {
        if (!response.ok) throw new Error("Snapshot request failed");
        return validateDemoSnapshot(await response.json());
      })
      .catch(() => {
        snapshotPromise = null;
        throw new ApiError("Public demonstration records could not be loaded.");
      });
  }
  return snapshotPromise;
}

export async function listDemoMachines(): Promise<Machine[]> {
  return (await loadDemoSnapshot()).machines;
}

export async function getDemoMachine(machineId: string): Promise<Machine> {
  const machine = (await loadDemoSnapshot()).machines.find((item) => item.id === machineId);
  if (!machine) throw new ApiError("The requested demonstration machine was not found.", 404);
  return machine;
}

export async function listDemoCapabilities(): Promise<ModelCapabilitiesResponse> {
  return (await loadDemoSnapshot()).capabilities;
}

export async function listDemoReports(
  machineId: string,
  limit: number,
  offset: number,
): Promise<MaintenanceReportSummary[]> {
  const snapshot = await loadDemoSnapshot();
  if (!snapshot.machines.some((machine) => machine.id === machineId)) {
    throw new ApiError("The requested demonstration machine was not found.", 404);
  }
  return snapshot.reports_by_machine[machineId]?.slice(offset, offset + limit) ?? [];
}

export async function getDemoReport(reportId: string): Promise<MaintenanceReport> {
  const report = (await loadDemoSnapshot()).reports[reportId];
  if (!report) throw new ApiError("The requested demonstration report was not found.", 404);
  return report;
}

export async function getDemoEvidence(reportId: string): Promise<MaintenanceReportEvidence> {
  const evidence = (await loadDemoSnapshot()).evidence[reportId];
  if (!evidence) throw new ApiError("Evidence for this demonstration report was not found.", 404);
  return evidence;
}
