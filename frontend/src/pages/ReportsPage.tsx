import { ArrowRight, FileClock } from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";

import { listMachines } from "../api/machines";
import { listMachineReports } from "../api/reports";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { PageTransition } from "../components/PageTransition";
import { SignatureHero } from "../components/SignatureHero";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { formatDate, humanize, shortId } from "../lib/format";

const PAGE_SIZE = 10;

export function ReportsPage() {
  const [chosenMachine, setChosenMachine] = useState("");
  const [page, setPage] = useState(0);
  const machinesLoader = useCallback((signal: AbortSignal) => listMachines(signal), []);
  const machines = useAsyncResource(machinesLoader);
  const machineId = chosenMachine || machines.data?.[0]?.id || "";
  const reportsLoader = useCallback((signal: AbortSignal) => machineId ? listMachineReports(machineId, PAGE_SIZE, page * PAGE_SIZE, signal) : Promise.resolve([]), [machineId, page]);
  const reports = useAsyncResource(reportsLoader);
  const names = new Map((machines.data ?? []).map((machine) => [machine.id, machine.name]));
  const selectedMachine = (machines.data ?? []).find((machine) => machine.id === machineId);
  const reportSceneItems = (reports.data ?? []).map((report) => ({
    label: humanize(report.condition),
    meta: formatDate(report.generated_at),
    tone: report.condition === "normal" ? "positive" as const : report.condition === "abnormal" ? "warning" as const : "neutral" as const,
  }));

  return (
    <PageTransition>
      <SignatureHero
        index="CHAPTER / 04"
        eyebrow="Maintenance reports / stored history"
        title={<>Historical <em>Intelligence</em></>}
        description="Move through verified maintenance artifacts in chronological depth. Opening a record performs no inference, retrieval, Decision Engine execution, or generation."
        variant="history"
        sceneKicker="Stored artifact corridor"
        sceneTitle={selectedMachine ? selectedMachine.name : "Historical report index"}
        sceneNote={reports.data ? `${reports.data.length} stored report${reports.data.length === 1 ? "" : "s"} on this page for the selected machine.` : "Waiting for the authoritative report index."}
        sceneItems={reportSceneItems}
        facts={
          <>
            <span><strong>{machines.data?.length ?? "—"}</strong> machines available for history</span>
            <span><strong>Read-only access</strong> no pipeline recomputation</span>
          </>
        }
      />
      {machines.loading && <LoadingState label="Loading machine index…" />}
      {machines.error && <ErrorState error={machines.error} onRetry={machines.reload} />}
      {machines.data && machines.data.length === 0 && <EmptyState title="No machines available" message="A persisted machine is required before reports can exist." />}
      {machines.data && machines.data.length > 0 && (
        <>
          <label className="machine-select glass-card"><span>Machine history</span><select value={machineId} onChange={(event) => { setChosenMachine(event.target.value); setPage(0); }}>{machines.data.map((machine) => <option key={machine.id} value={machine.id}>{machine.name} / {machine.asset_type}</option>)}</select></label>
          {reports.loading && <LoadingState label="Loading stored maintenance reports…" />}
          {reports.error && <ErrorState error={reports.error} onRetry={reports.reload} />}
          {reports.data?.length === 0 && <EmptyState title="No reports yet" message="Run an analysis from this machine's workspace to create its first verified record." action={<Link className="button button--primary" to={`/machines/${machineId}`}>Open machine</Link>} />}
          {reports.data && reports.data.length > 0 && <section className="report-index history-corridor glass-panel" aria-label="Stored maintenance report timeline"><div className="history-corridor__head"><div><p className="eyebrow">Chronological stored artifacts</p><h2>Report timeline</h2></div><span>Newest first / authoritative records</span></div><div className="history-corridor__axis" aria-hidden="true" />{reports.data.map((report, index) => <Link to={`/reports/${report.report_id}`} className="report-index__row" key={report.report_id}><span className="history-corridor__node" aria-hidden="true"><FileClock /></span><div><small>Artifact {String(page * PAGE_SIZE + index + 1).padStart(2, "0")}</small><strong>{humanize(report.condition)}</strong><p>{report.executive_summary}</p><code>{shortId(report.report_id)}</code></div><StatusBadge tone={report.generation_status === "fallback" ? "warning" : "accent"}>{humanize(report.generation_status)}</StatusBadge><div><time>{formatDate(report.generated_at)}</time><small>{names.get(report.machine_id) ?? shortId(report.machine_id)}</small></div><ArrowRight aria-hidden="true" /></Link>)}</section>}
          {reports.data && reports.data.length > 0 && <div className="pagination"><button className="button button--secondary" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {page + 1}</span><button className="button button--secondary" type="button" disabled={reports.data.length < PAGE_SIZE} onClick={() => setPage((value) => value + 1)}>Next</button></div>}
        </>
      )}
    </PageTransition>
  );
}
