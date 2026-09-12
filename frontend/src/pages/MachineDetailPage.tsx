import { motion } from "framer-motion";
import { Activity, ArrowRight, CalendarClock, Play } from "lucide-react";
import { useCallback, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { listModelCapabilities } from "../api/capabilities";
import { PUBLIC_DEMO } from "../api/demo";
import { getMachine } from "../api/machines";
import { getMaintenanceReport, getMaintenanceReportEvidence, listMachineReports } from "../api/reports";
import type { MaintenanceReport, MaintenanceReportEvidence } from "../api/types";
import { AnalysisDrawer } from "../components/AnalysisDrawer";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { PageTransition } from "../components/PageTransition";
import { ReportView } from "../components/ReportView";
import { SignatureHero } from "../components/SignatureHero";
import { StatusBadge } from "../components/StatusBadge";
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
  const latestSummary = history.data?.[0];
  const latestFinding = latest.data?.report.analysis.findings[0];
  const producingModel = latest.data?.report.producing_models[0];
  const sceneItems = [
    latestSummary ? {
      label: humanize(latestSummary.condition),
      meta: "stored condition",
      tone: latestSummary.condition === "normal" ? "positive" as const : latestSummary.condition === "abnormal" ? "warning" as const : "neutral" as const,
    } : null,
    latestFinding ? { label: humanize(latestFinding.modality), meta: latestFinding.code, tone: "accent" as const } : null,
    producingModel ? { label: producingModel.model_id, meta: "producing model", tone: "positive" as const } : null,
  ].filter((item): item is NonNullable<typeof item> => item !== null);

  return (
    <PageTransition>
      <SignatureHero
        index="CHAPTER / 03"
        eyebrow={`${machine.data.asset_type} / machine intelligence`}
        title={<motion.span layoutId={`machine-name-${machine.data.id}`}>{machine.data.name}</motion.span>}
        description="An evidence-bounded workspace for one persisted asset. Visual geometry is architectural; stored reports remain the only source of condition and finding context."
        variant="machine"
        sceneKicker="Machine intelligence halo"
        sceneTitle={latestSummary ? `${humanize(latestSummary.condition)} / stored record` : "Condition not determined"}
        sceneNote={latestSummary ? `Latest authoritative report stored ${formatDate(latestSummary.generated_at)}.` : "No stored report has established condition for this asset."}
        sceneItems={sceneItems}
        facts={
          <>
            <span><strong>Machine ID</strong><code>{machine.data.id}</code></span>
            {latestFinding && <span><strong>Latest finding</strong>{latestFinding.code}</span>}
          </>
        }
        actions={PUBLIC_DEMO
          ? <button className="button button--secondary" type="button" disabled title="The public demonstration is read only"><Play size={16} /> Analysis disabled in public demo</button>
          : <button className="button button--primary" type="button" onClick={() => setDrawerOpen(true)}><Play size={16} /> Run Analysis</button>}
      />

      {history.loading && <LoadingState label="Loading stored report history…" />}
      {history.error && <ErrorState error={history.error} onRetry={history.reload} />}
      {page === 0 && latest.loading && history.data && history.data.length > 0 && <LoadingState label="Verifying latest report and evidence…" />}
      {page === 0 && latest.error && <ErrorState error={latest.error} onRetry={latest.reload} />}
      {page === 0 && latest.data && <ReportView report={latest.data.report} evidence={latest.data.evidence} />}
      {page === 0 && history.data?.length === 0 && <EmptyState title="No reports yet" message={PUBLIC_DEMO ? "This exported demonstration machine has no stored reports." : "Run an analysis to create the first verified maintenance record."} action={PUBLIC_DEMO ? undefined : <button className="button button--primary" type="button" onClick={() => setDrawerOpen(true)}>Run Analysis</button>} />}

      {history.data && history.data.length > 0 && (
        <section className="history-section glass-panel" aria-labelledby="machine-history-title">
          <div className="section-heading"><div><p className="eyebrow">Stored authoritative records</p><h2 id="machine-history-title">Report history</h2></div><CalendarClock aria-hidden="true" /></div>
          <div className="history-list history-list--timeline">
            {history.data.map((report, index) => <Link to={`/reports/${report.report_id}`} key={report.report_id}><span className="history-list__node" aria-hidden="true"><Activity /></span><div><small>Record {String(page * PAGE_SIZE + index + 1).padStart(2, "0")}</small><strong>{humanize(report.condition)}</strong><span>{report.executive_summary}</span></div><div><StatusBadge tone={report.generation_status === "fallback" ? "warning" : "accent"}>{humanize(report.generation_status)}</StatusBadge><small>Report generated</small><time dateTime={report.generated_at} title={report.generated_at}>{formatDate(report.generated_at)}</time><code>{shortId(report.report_id)}</code></div><ArrowRight aria-hidden="true" /></Link>)}
          </div>
          <div className="pagination"><button className="button button--secondary" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {page + 1}</span><button className="button button--secondary" type="button" disabled={history.data.length < PAGE_SIZE} onClick={() => setPage((value) => value + 1)}>Next</button></div>
        </section>
      )}

      {!PUBLIC_DEMO && <AnalysisDrawer open={drawerOpen} machineId={machine.data.id} machineName={machine.data.name} capabilities={capabilities.data?.models ?? []} onClose={() => setDrawerOpen(false)} onCreated={onCreated} />}
    </PageTransition>
  );
}
