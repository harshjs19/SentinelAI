import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronDown, Cpu, Radio } from "lucide-react";
import { useCallback, useState } from "react";

import { listModelCapabilities } from "../api/capabilities";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { PageHeader } from "../components/PageHeader";
import { PageTransition } from "../components/PageTransition";
import { lifecycleTone } from "../components/badgeTone";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { humanize } from "../lib/format";

export function ModelsPage() {
  const reduced = useReducedMotion();
  const [expanded, setExpanded] = useState<string | null>(null);
  const loader = useCallback((signal: AbortSignal) => listModelCapabilities(signal), []);
  const capabilities = useAsyncResource(loader);

  return (
    <PageTransition>
      <PageHeader eyebrow="Transparent model governance" title="Model Capabilities" description="Validated, experimental, and rejected experiments remain visible as distinct engineering results." />
      {capabilities.loading && <LoadingState label="Loading authoritative capability registry…" />}
      {capabilities.error && <ErrorState error={capabilities.error} onRetry={capabilities.reload} />}
      {capabilities.data?.models.length === 0 && <EmptyState title="No registered capabilities" message="The backend returned no model capability records." />}
      <section className="capability-grid">
        {capabilities.data?.models.map((model) => {
          const open = expanded === model.model_id;
          return <article className={`capability-card glass-card lifecycle-${model.status}`} key={model.model_id}>
            <button type="button" aria-expanded={open} onClick={() => setExpanded(open ? null : model.model_id)}>
              <span className="capability-card__icon"><Cpu aria-hidden="true" /></span>
              <span className="capability-card__title"><small>{humanize(model.modality)}</small><code>{model.model_id}</code></span>
              <StatusBadge tone={lifecycleTone(model.status)}>{humanize(model.status)}</StatusBadge>
              {model.runtime_default && <span className="runtime-pill"><Radio aria-hidden="true" /> Runtime default</span>}
              <ChevronDown aria-hidden="true" />
            </button>
            <AnimatePresence initial={false}>{open && <motion.div className="capability-card__details" initial={reduced ? false : { opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={reduced ? undefined : { opacity: 0, height: 0 }} transition={{ duration: reduced ? 0 : 0.22 }}><dl><div><dt>Validated scope</dt><dd>{model.validated_scope}</dd></div><div><dt>Confidence semantics</dt><dd>{humanize(model.confidence_semantics)}</dd></div><div><dt>Evaluation reference</dt><dd><code>{model.evaluation_reference}</code></dd></div></dl>{model.status === "rejected_experiment" && <p>Preserved as a rejected experimental result; it is not a production capability.</p>}{model.status === "experimental" && <p>Experimental capability. Its validated scope and limitations remain binding.</p>}</motion.div>}</AnimatePresence>
          </article>;
        })}
      </section>
    </PageTransition>
  );
}
