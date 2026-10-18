import { createContext, useContext } from "react";

import type { MaintenanceReport, MaintenanceSubmission } from "../api/types";

export interface PendingReportOperation {
  machineId: string;
  submission: MaintenanceSubmission;
  idempotencyKey: string;
  status: "submitting" | "uncertain";
}

export type ReportOperation = PendingReportOperation | {
  machineId: string;
  idempotencyKey: string;
  status: "succeeded";
  report: MaintenanceReport;
};

export type SubmissionResult =
  | { kind: "success"; report: MaintenanceReport }
  | { kind: "uncertain" }
  | { kind: "rejected"; message: string }
  | { kind: "busy" };

export interface SubmissionContextValue {
  operation: ReportOperation | null;
  submit: (machineId: string, submission: MaintenanceSubmission) => Promise<SubmissionResult>;
  retry: (machineId: string) => Promise<SubmissionResult>;
  acknowledgeSuccess: (machineId: string) => void;
}

export const SubmissionContext = createContext<SubmissionContextValue | null>(null);

export function useMaintenanceSubmission(): SubmissionContextValue {
  const context = useContext(SubmissionContext);
  if (!context) throw new Error("Maintenance submission owner is missing");
  return context;
}
