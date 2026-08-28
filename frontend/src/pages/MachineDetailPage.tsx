import { Activity, ArrowRight, CalendarClock, Play, ServerCog } from "lucide-react";
import { useCallback, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { listModelCapabilities } from "../api/capabilities";
import { getMachine } from "../api/machines";
import { getMaintenanceReport, getMaintenanceReportEvidence, listMachineReports } from "../api/reports";
import type { MaintenanceReport, MaintenanceReportEvidence } from "../api/types";
import { AnalysisDrawer } from "../components/AnalysisDrawer";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { PageTransition } from "../components/PageTransition";
import { ReportView } from "../components/ReportView";
import { StatusBadge } from "../components/StatusBadge";
import { conditionTone } from "../components/badgeTone";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { formatDate, humanize, shortId } from "../lib/format";

const PAGE_SIZE = 6;

export function MachineDetailPage() {
  const { machineId = "" } = useParams();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [page, setPage] = useState(0);
  const machineLoader = useCallback((signal: AbortSignal) => getMachine(machineId, signal), [machineId]);
  const historyLoader = useCallback((signal: AbortSignal) => listMachineReports(machineId, PAGE_SIZE, page * PAGE_SIZE, signal), [machineId, page]);
  const capabilitiesLoader = useCallback((signal: AbortSignal) => listModelCapabilities(signal), []);
  const machine = useAsyncResource(machineLoader);
  const history = useAsyncResource(historyLoader);
  const capabilities = useAsyncResource(capabilitiesLoader);
  const latestId = page === 0 ? history.data?.[0]?.report_id : undefined;
  const latestLoader = useCallback(async (signal: AbortSignal): Promise<{ report: MaintenanceReport; evidence: MaintenanceReportEvidence } | null> => {
    if (!latestId) return null;
    const [report, evidence] = await Promise.all([getMaintenanceReport(latestId, signal), getMaintenanceReportEvidence(latestId, signal)]);
    return { report, evidence };
  }, [latestId]);
  const latest = useAsyncResource(latestLoader);

  if (machine.loading) return <LoadingState label="Opening machine intelligence workspace…" />;
  if (machine.error) return <ErrorState error={machine.error} onRetry={machine.reload} />;
  if (!machine.data) return null;

  const onCreated = (report: MaintenanceReport) => {
    setDrawerOpen(false);
    navigate(`/reports/${report.report_id}`);
  };

  return (
    <PageTransition>
      <section className="machine-hero glass-panel">
        <div className="machine-hero__icon"><ServerCog aria-hidden="true" /></div>
        <div className="machine-hero__identity"><p className="eyebrow">{machine.data.asset_type}</p><h1>{machine.data.name}</h1><code>{machine.data.id}</code></div>
        <div className="machine-hero__condition">
          {history.data?.[0] ? <><span>Latest stored condition</span><StatusBadge tone={conditionTone(history.data[0].condition)}>{humanize(history.data[0].condition)}</StatusBadge><small>{formatDate(history.data[0].generated_at)}</small></> : <><span>Latest stored condition</span><strong>Not determined</strong><small>No stored report loaded</small></>}
        </div>
        <button className="button button--primary" type="button" onClick={() => setDrawerOpen(true)}><Play size={16} /> Run Analysis</button>
      </section>

      {history.loading && <LoadingState label="Loading stored report history…" />}
      {history.error && <ErrorState error={history.error} onRetry={history.reload} />}
      {page === 0 && latest.loading && history.data && history.data.length > 0 && <LoadingState label="Verifying latest report and evidence…" />}
      {page === 0 && latest.error && <ErrorState error={latest.error} onRetry={latest.reload} />}
      {page === 0 && latest.data && <ReportView report={latest.data.report} evidence={latest.data.evidence} />}
      {page === 0 && history.data?.length === 0 && <EmptyState title="No reports yet" message="Run an analysis to create the first verified maintenance record." action={<button className="button button--primary" type="button" onClick={() => setDrawerOpen(true)}>Run Analysis</button>} />}

      {history.data && history.data.length > 0 && (
        <section className="history-section glass-panel" aria-labelledby="machine-history-title">
          <div className="section-heading"><div><p className="eyebrow">Stored authoritative records</p><h2 id="machine-history-title">Report history</h2></div><CalendarClock aria-hidden="true" /></div>
          <div className="history-list">
            {history.data.map((report) => <Link to={`/reports/${report.report_id}`} key={report.report_id}><Activity aria-hidden="true" /><div><strong>{humanize(report.condition)}</strong><span>{report.executive_summary}</span></div><div><StatusBadge tone={report.generation_status === "fallback" ? "warning" : "accent"}>{humanize(report.generation_status)}</StatusBadge><time>{formatDate(report.generated_at)}</time><code>{shortId(report.report_id)}</code></div><ArrowRight aria-hidden="true" /></Link>)}
          </div>
          <div className="pagination"><button className="button button--secondary" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {page + 1}</span><button className="button button--secondary" type="button" disabled={history.data.length < PAGE_SIZE} onClick={() => setPage((value) => value + 1)}>Next</button></div>
        </section>
      )}

      <AnalysisDrawer open={drawerOpen} machineId={machine.data.id} machineName={machine.data.name} capabilities={capabilities.data?.models ?? []} onClose={() => setDrawerOpen(false)} onCreated={onCreated} />
    </PageTransition>
  );
}
