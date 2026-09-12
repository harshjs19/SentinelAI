import { listModelCapabilities } from "./capabilities";
import { listMachines } from "./machines";
import { getMaintenanceReport, getMaintenanceReportEvidence, listMachineReports } from "./reports";
import type {
  MaintenanceReport,
  MaintenanceReportEvidence,
  MaintenanceReportSummary,
  Machine,
  ModelCapability,
} from "./types";

const PAGE_SIZE = 100;

export interface DashboardOverview {
  machines: Machine[];
  models: ModelCapability[];
  reports: MaintenanceReportSummary[];
  latest: {
    summary: MaintenanceReportSummary;
    report: MaintenanceReport;
    evidence: MaintenanceReportEvidence;
    machine: Machine;
  } | null;
}

async function listAllReports(machineId: string, signal: AbortSignal) {
  const records: MaintenanceReportSummary[] = [];
  let offset = 0;
  for (;;) {
    const page = await listMachineReports(machineId, PAGE_SIZE, offset, signal);
    records.push(...page);
    if (page.length < PAGE_SIZE) return records;
    offset += page.length;
  }
}

export async function getDashboardOverview(signal: AbortSignal): Promise<DashboardOverview> {
  const [machines, capabilities] = await Promise.all([
    listMachines(signal),
    listModelCapabilities(signal),
  ]);
  const reportGroups = await Promise.all(
    machines.map((machine) => listAllReports(machine.id, signal)),
  );
  const reports = reportGroups.flat().sort(
    (left, right) => Date.parse(right.generated_at) - Date.parse(left.generated_at),
  );
  const summary = reports[0];
  if (!summary) return { machines, models: capabilities.models, reports, latest: null };

  const machine = machines.find((candidate) => candidate.id === summary.machine_id);
  if (!machine) throw new Error("A stored report references an unavailable machine record.");
  const [report, evidence] = await Promise.all([
    getMaintenanceReport(summary.report_id, signal),
    getMaintenanceReportEvidence(summary.report_id, signal),
  ]);
  return {
    machines,
    models: capabilities.models,
    reports,
    latest: { summary, report, evidence, machine },
  };
}
