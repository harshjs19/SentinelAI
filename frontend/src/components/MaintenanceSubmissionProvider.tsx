import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { createIdempotencyKey, createMaintenanceReport } from "../api/reports";
import type { MaintenanceSubmission } from "../api/types";
import { SubmissionContext, type PendingReportOperation, type ReportOperation, type SubmissionResult } from "./maintenanceSubmissionContext";

export function MaintenanceSubmissionProvider({ children }: { children: ReactNode }) {
  const [operation, setOperation] = useState<ReportOperation | null>(null);
  const operationRef = useRef<ReportOperation | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const update = useCallback((next: ReportOperation | null) => {
    operationRef.current = next;
    if (mountedRef.current) setOperation(next);
  }, []);

  const execute = useCallback(async (request: PendingReportOperation, wasUncertain: boolean): Promise<SubmissionResult> => {
    try {
      const report = await createMaintenanceReport(request.machineId, request.submission, request.idempotencyKey);
      if (mountedRef.current && operationRef.current?.idempotencyKey === request.idempotencyKey) {
        update({ machineId: request.machineId, idempotencyKey: request.idempotencyKey, status: "succeeded", report });
      }
      return { kind: "success", report };
    } catch (reason) {
      const uncertain = wasUncertain || !(reason instanceof ApiError)
        || reason.transportUncertain || reason.status === 409
        || (reason.status >= 200 && reason.status < 300)
        || reason.status >= 500;
      if (mountedRef.current && operationRef.current?.idempotencyKey === request.idempotencyKey) {
        update(uncertain ? { ...request, status: "uncertain" } : null);
      }
      return uncertain
        ? { kind: "uncertain" }
        : { kind: "rejected", message: reason instanceof ApiError ? reason.message : "The report could not be created." };
    }
  }, [update]);

  const submit = useCallback((machineId: string, submission: MaintenanceSubmission): Promise<SubmissionResult> => {
    if (operationRef.current) return Promise.resolve({ kind: "busy" });
    const request: PendingReportOperation = {
      machineId,
      submission,
      idempotencyKey: createIdempotencyKey(),
      status: "submitting",
    };
    update(request);
    return execute(request, false);
  }, [execute, update]);

  const retry = useCallback((machineId: string): Promise<SubmissionResult> => {
    const request = operationRef.current;
    if (!request || request.machineId !== machineId || request.status !== "uncertain") {
      return Promise.resolve({ kind: "busy" });
    }
    update({ ...request, status: "submitting" });
    return execute(request, true);
  }, [execute, update]);

  const acknowledgeSuccess = useCallback((machineId: string) => {
    if (operationRef.current?.machineId === machineId && operationRef.current.status === "succeeded") {
      update(null);
    }
  }, [update]);

  const value = useMemo(() => ({ operation, submit, retry, acknowledgeSuccess }), [operation, submit, retry, acknowledgeSuccess]);
  return <SubmissionContext.Provider value={value}>{children}</SubmissionContext.Provider>;
}
