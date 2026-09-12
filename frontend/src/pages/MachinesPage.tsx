import { motion, useReducedMotion } from "framer-motion";
import { ArrowUpRight, Search, ServerCog } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { listMachines } from "../api/machines";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { PageTransition } from "../components/PageTransition";
import { SignatureHero } from "../components/SignatureHero";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { motionDuration, premiumEase } from "../lib/motion";

const MotionLink = motion.create(Link);

export function MachinesPage() {
  const reduced = useReducedMotion();
  const [query, setQuery] = useState("");
  const loader = useCallback((signal: AbortSignal) => listMachines(signal), []);
  const machines = useAsyncResource(loader);
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return machines.data ?? [];
    return (machines.data ?? []).filter((machine) => `${machine.name} ${machine.asset_type} ${machine.id}`.toLowerCase().includes(normalized));
  }, [machines.data, query]);
  const assetTypes = useMemo(
    () => Array.from(new Set((machines.data ?? []).map((machine) => machine.asset_type))).sort(),
    [machines.data],
  );

  return (
    <PageTransition>
      <SignatureHero
        index="CHAPTER / 02"
        eyebrow="Machines / authoritative inventory"
        title={<>Stored <em>Machines</em></>}
        description="Browse authoritative machine identities. Condition appears only where a persisted analysis report supports it."
        variant="fleet"
        sceneKicker="Representational asset field"
        sceneTitle={machines.data ? `${machines.data.length} persisted assets` : "Authoritative asset field"}
        sceneNote="Nodes represent stored machine identities only. They are not live network, telemetry, or health indicators."
        sceneItems={assetTypes.map((label) => ({ label: `Asset class / ${label}`, meta: "persisted", tone: "accent" }))}
        facts={machines.data ? (
          <>
            <span><strong>{machines.data.length}</strong> persisted machine records</span>
            <span><strong>Stored reports only</strong> determine displayed condition</span>
          </>
        ) : undefined}
      />
      {machines.data && <div className="fleet-toolbar">
        <div className="fleet-toolbar__count"><span>Filtered machine records</span><strong>{filtered.length} visible / {machines.data.length} stored</strong></div>
        <label className="search-box glass-card"><Search aria-hidden="true" /><span className="sr-only">Search machines</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, asset type, or ID" /></label>
      </div>}
      {machines.loading && <LoadingState label="Loading machine inventory…" />}
      {machines.error && <ErrorState error={machines.error} onRetry={machines.reload} />}
      {machines.data && machines.data.length === 0 && <EmptyState title="No machines yet" message="Create a machine through the authoritative backend API before running analysis." />}
      {machines.data && machines.data.length > 0 && filtered.length === 0 && <EmptyState title="No matching machines" message="Adjust the local search filter. No machine data has been changed." />}
      <section className="machine-grid" aria-label="Machines">
        {filtered.map((machine, index) => (
          <MotionLink
            className="machine-card glass-card"
            to={`/machines/${machine.id}`}
            key={machine.id}
            layoutId={`machine-card-${machine.id}`}
            whileHover={reduced ? undefined : { y: -2 }}
            transition={{ duration: reduced ? 0 : motionDuration.fast, ease: premiumEase }}
          >
            <span className="machine-card__index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            <span className="machine-card__architecture" aria-hidden="true"><i /><i /><i /></span>
            <div className="machine-card__icon"><ServerCog aria-hidden="true" /></div>
            <div className="machine-card__body"><p className="eyebrow">{machine.asset_type}</p><motion.h2 layoutId={`machine-name-${machine.id}`}>{machine.name}</motion.h2><code>{machine.id}</code></div>
            <div className="machine-card__action"><span>Open workspace</span><ArrowUpRight aria-hidden="true" /></div>
            <p className="machine-card__boundary">Condition is shown only when a stored report exists.</p>
          </MotionLink>
        ))}
      </section>
    </PageTransition>
  );
}
