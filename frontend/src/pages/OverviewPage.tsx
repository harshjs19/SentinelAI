import { Activity, ArrowRight, Boxes, FileClock } from "lucide-react";
import { useCallback } from "react";
import { Link } from "react-router-dom";

import { PUBLIC_DEMO } from "../api/demo";
import { getDashboardOverview } from "../api/overview";
import type { ConditionState } from "../api/types";
import { CapabilityChart } from "../components/CapabilityChart";
import { MetricCard } from "../components/MetricCard";
import { PageTransition } from "../components/PageTransition";
import { SentinelCore } from "../components/SentinelCore";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { conditionTone } from "../components/badgeTone";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { usePointerSpotlight } from "../hooks/usePointerSpotlight";
import { formatDate, humanize } from "../lib/format";

const CONDITIONS: ConditionState[] = ["normal", "abnormal", "indeterminate"];

export function OverviewPage() {
  const heroSpotlight = usePointerSpotlight<HTMLElement>();
  const loader = useCallback((signal: AbortSignal) => getDashboardOverview(signal), []);
  const overview = useAsyncResource(loader);
  const data = overview.data;
  const conditionCounts = data
    ? Object.fromEntries(
        CONDITIONS.map((condition) => [
          condition,
          data.reports.filter((report) => report.condition === condition).length,
        ]),
      ) as Record<ConditionState, number>
    : null;
  const latestFinding = data?.latest?.report.analysis.findings[0];
  const latestModel = data?.latest?.report.producing_models[0];

  return (
    <PageTransition>
      <section
        ref={heroSpotlight.ref}
        onPointerMove={heroSpotlight.onPointerMove}
        className="overview-hero glass-panel spotlight-surface"
      >
        <div className="overview-hero__copy">
          <p className="eyebrow">Evidence-bounded industrial analysis</p>
          <span className="hero-index" aria-hidden="true">SYSTEM / 01</span>
          <h1>Stored machine analyses with <em>verifiable provenance.</em></h1>
          <p>
            Review persisted reports, producing models, and evidence lineage. SentinelAI does
            not infer health, severity, operational risk, failure probability, or remaining
            useful life from classifier confidence.
          </p>
          <div className="hero-actions">
            <Link className="button button--primary" to="/machines">
              Inspect machines <ArrowRight size={16} />
            </Link>
            <Link className="button button--secondary" to="/models">Review model evidence</Link>
          </div>
          <div className="hero-proof">
            <Activity aria-hidden="true" />
            <span>Single-modality records / stored lineage / explicit limitations</span>
          </div>
        </div>
        <SentinelCore />
      </section>

      {overview.loading && <LoadingState label="Loading stored workspace records…" />}
      {overview.error && <ErrorState error={overview.error} onRetry={overview.reload} />}

      {data && (
        <>
          <section className="metric-row metric-row--meaningful" aria-label="Stored record summary">
            <MetricCard
              icon={Boxes}
              label={PUBLIC_DEMO ? "Demo machines" : "Persisted machines"}
              value={data.machines.length}
              note={PUBLIC_DEMO ? "Exported machine records" : "Authoritative machine records"}
            />
            <MetricCard
              icon={FileClock}
              label="Stored reports"
              value={data.reports.length}
              note="Exact report count across the displayed machines"
            />
          </section>

          <section className="overview-evidence-grid" aria-label="Analysis and model summary">
            <article className="summary-panel glass-card">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Stored report summaries</p>
                  <h2>Analysis conditions</h2>
                </div>
              </div>
              {data.reports.length > 0 ? (
                <dl className="condition-counts">
                  {CONDITIONS.map((condition) => (
                    <div key={condition}>
                      <dt>{humanize(condition)}</dt>
                      <dd>{conditionCounts?.[condition]}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="subdued-copy">
                  No condition counts are shown because no stored analysis reports exist.
                </p>
              )}
              <p className="data-source-note">One persisted report summary contributes one condition.</p>
            </article>

            <article className="summary-panel glass-card">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Latest stored lineage</p>
                  <h2>Recent analysis</h2>
                </div>
              </div>
              {data.latest ? (
                <dl className="recent-analysis">
                  <div><dt>Machine</dt><dd>{data.latest.machine.name}</dd></div>
                  <div>
                    <dt>Condition</dt>
                    <dd><StatusBadge tone={conditionTone(data.latest.summary.condition)}>{humanize(data.latest.summary.condition)}</StatusBadge></dd>
                  </div>
                  {latestFinding && <div><dt>Modality</dt><dd>{humanize(latestFinding.modality)}</dd></div>}
                  {latestModel && <div><dt>Producing model</dt><dd><code>{latestModel.model_id}</code></dd></div>}
                  <div>
                    <dt>Analysis created</dt>
                    <dd><time dateTime={data.latest.evidence.analysis.created_at} title={data.latest.evidence.analysis.created_at}>{formatDate(data.latest.evidence.analysis.created_at)}</time></dd>
                  </div>
                </dl>
              ) : (
                <p className="subdued-copy">No recent analysis exists because no reports are stored.</p>
              )}
              <p className="data-source-note">Loaded from the stored report and evidence endpoints.</p>
            </article>

            <CapabilityChart models={data.models} />
          </section>
        </>
      )}
    </PageTransition>
  );
}
