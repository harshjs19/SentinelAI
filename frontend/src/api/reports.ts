import { apiRequest } from "./client";
import type {
  MaintenanceReport,
  MaintenanceReportEvidence,
  MaintenanceReportSummary,
  MaintenanceSubmission,
} from "./types";

export function createIdempotencyKey(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

export async function createMaintenanceReport(
  machineId: string,
  submission: MaintenanceSubmission,
  idempotencyKey: string,
): Promise<MaintenanceReport> {
  const path = `/machines/${encodeURIComponent(machineId)}/maintenance-reports/${submission.modality}`;
  const headers: Record<string, string> = { "Idempotency-Key": idempotencyKey };

  if (submission.modality === "timeseries") {
    headers["Content-Type"] = "application/json";
    return apiRequest<MaintenanceReport>(path, {
      method: "POST",
      headers,
      body: JSON.stringify({
        samples: submission.samples,
        intent: submission.intent,
        question: submission.question?.trim() || null,
      }),
    });
  }

  const form = new FormData();
  form.append("file", submission.file);
  form.append("intent", submission.intent);
  if (submission.question?.trim()) form.append("question", submission.question.trim());
  return apiRequest<MaintenanceReport>(path, {
    method: "POST",
    headers,
    body: form,
  });
}

export function getMaintenanceReport(
  reportId: string,
  signal?: AbortSignal,
): Promise<MaintenanceReport> {
  return apiRequest<MaintenanceReport>(
    `/maintenance-reports/${encodeURIComponent(reportId)}`,
    { signal },
  );
}

export function getMaintenanceReportEvidence(
  reportId: string,
  signal?: AbortSignal,
): Promise<MaintenanceReportEvidence> {
  return apiRequest<MaintenanceReportEvidence>(
    `/maintenance-reports/${encodeURIComponent(reportId)}/evidence`,
    { signal },
  );
}

export function listMachineReports(
  machineId: string,
  limit = 10,
  offset = 0,
  signal?: AbortSignal,
): Promise<MaintenanceReportSummary[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiRequest<MaintenanceReportSummary[]>(
    `/machines/${encodeURIComponent(machineId)}/maintenance-reports?${params}`,
    { signal },
  );
}

