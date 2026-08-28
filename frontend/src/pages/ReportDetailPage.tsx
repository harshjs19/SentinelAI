import { ArrowLeft } from "lucide-react";
import { useCallback } from "react";
import { Link, useParams } from "react-router-dom";

import { getMaintenanceReport, getMaintenanceReportEvidence } from "../api/reports";
import type { MaintenanceReport, MaintenanceReportEvidence } from "../api/types";
import { ErrorState, LoadingState } from "../components/States";
import { PageTransition } from "../components/PageTransition";
import { ReportView } from "../components/ReportView";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { shortId } from "../lib/format";

export function ReportDetailPage() {
  const { reportId = "" } = useParams();
  const loader = useCallback(async (signal: AbortSignal): Promise<{ report: MaintenanceReport; evidence: MaintenanceReportEvidence }> => {
    const [report, evidence] = await Promise.all([getMaintenanceReport(reportId, signal), getMaintenanceReportEvidence(reportId, signal)]);
    return { report, evidence };
  }, [reportId]);
  const resource = useAsyncResource(loader);

  return (
    <PageTransition>
      <div className="detail-toolbar"><Link to="/reports"><ArrowLeft size={15} /> Maintenance history</Link><code>Report {shortId(reportId)}</code></div>
      {resource.loading && <LoadingState label="Verifying stored report lineage…" />}
      {resource.error && <ErrorState error={resource.error} onRetry={resource.reload} />}
      {resource.data && <ReportView report={resource.data.report} evidence={resource.data.evidence} />}
    </PageTransition>
  );
}
