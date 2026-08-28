import { useCallback } from "react";
import { ArrowRight, Boxes, Cpu, FlaskConical, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { listModelCapabilities } from "../api/capabilities";
import { listMachines } from "../api/machines";
import { AssetChart } from "../components/AssetChart";
import { CapabilityChart } from "../components/CapabilityChart";
import { ErrorState, LoadingState } from "../components/States";
import { MetricCard } from "../components/MetricCard";
import { PageTransition } from "../components/PageTransition";
import { SentinelCore } from "../components/SentinelCore";
import { useAsyncResource } from "../hooks/useAsyncResource";

export function OverviewPage() {
  const machinesLoader = useCallback((signal: AbortSignal) => listMachines(signal), []);
  const modelsLoader = useCallback((signal: AbortSignal) => listModelCapabilities(signal), []);
  const machines = useAsyncResource(machinesLoader);
  const capabilities = useAsyncResource(modelsLoader);

  return (
    <PageTransition>
      <section className="overview-hero glass-panel">
        <div className="overview-hero__copy">
          <p className="eyebrow">Evidence-bounded industrial AI</p>
          <h1>Industrial intelligence grounded in <em>evidence, provenance,</em> and bounded reasoning.</h1>
          <p>SentinelAI turns one machine signal at a time into a verified maintenance record without inventing operational certainty.</p>
          <div className="hero-actions">
            <Link className="button button--primary" to="/machines">Open machine intelligence <ArrowRight size={16} /></Link>
            <Link className="button button--secondary" to="/models">Inspect model registry</Link>
          </div>
          <div className="hero-proof"><ShieldCheck aria-hidden="true" /><span>Single-modality analysis / historical lineage / deterministic safety boundaries</span></div>
        </div>
        <SentinelCore />
      </section>

      {(machines.loading || capabilities.loading) && <LoadingState label="Loading authoritative workspace data…" />}
      {machines.error && <ErrorState error={machines.error} onRetry={machines.reload} />}
      {capabilities.error && <ErrorState error={capabilities.error} onRetry={capabilities.reload} />}

      {machines.data && capabilities.data && (
        <>
          <section className="metric-row" aria-label="Workspace summary">
            <MetricCard icon={Boxes} label="Persisted machines" value={String(machines.data.length)} note="Authoritative machine records" />
            <MetricCard icon={Cpu} label="Registered models" value={String(capabilities.data.models.length)} note="Visible across all lifecycle states" />
            <MetricCard icon={FlaskConical} label="Runtime defaults" value={String(capabilities.data.models.filter((model) => model.runtime_default).length)} note="Current capability registry" />
            <MetricCard icon={ShieldCheck} label="Validated baselines" value={String(capabilities.data.models.filter((model) => model.status === "validated_baseline").length)} note="Experimental remains distinct" />
          </section>
          <section className="overview-charts">
            <CapabilityChart models={capabilities.data.models} />
            <AssetChart machines={machines.data} />
          </section>
        </>
      )}
    </PageTransition>
  );
}
