import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronDown, Cpu, Radio } from "lucide-react";
import { useCallback, useState } from "react";

import { listModelCapabilities } from "../api/capabilities";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { PageTransition } from "../components/PageTransition";
import { SignatureHero } from "../components/SignatureHero";
import { lifecycleTone } from "../components/badgeTone";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { humanize } from "../lib/format";
import { motionDuration, premiumEase } from "../lib/motion";

export function ModelsPage() {
  const reduced = useReducedMotion();
  const [expanded, setExpanded] = useState<string | null>(null);
  const loader = useCallback((signal: AbortSignal) => listModelCapabilities(signal), []);
  const capabilities = useAsyncResource(loader);

  return (
    <PageTransition>
      <SignatureHero
        index="CHAPTER / 06"
        eyebrow="Model capabilities / transparent governance"
        title={<>Model <em>Governance</em></>}
        description="Inspect the declared capability constellation without collapsing validated baselines, experimental work, and rejected experiments into one status."
        variant="models"
        sceneKicker="Capability constellation"
        sceneTitle={capabilities.data ? `${capabilities.data.models.length} declared model records` : "Authoritative capability registry"}
        sceneNote="Spatial grouping communicates lifecycle identity only; it does not imply model fusion, ensemble execution, or live inference."
        sceneItems={(capabilities.data?.models ?? []).map((model) => ({
          label: humanize(model.modality),
          meta: `Lifecycle / ${humanize(model.status)}`,
          tone: model.status === "validated_baseline" ? "positive" : model.status === "experimental" ? "warning" : "danger",
        }))}
        facts={
          <>
            <span><strong>{capabilities.data?.models.filter((model) => model.runtime_default).length ?? "—"}</strong> runtime-default declarations</span>
            <span><strong>Lifecycle transparent</strong> rejected results stay visible</span>
          </>
        }
      />
      {capabilities.loading && <LoadingState label="Loading authoritative capability registry…" />}
      {capabilities.error && <ErrorState error={capabilities.error} onRetry={capabilities.reload} />}
      {capabilities.data?.models.length === 0 && <EmptyState title="No registered capabilities" message="The backend returned no model capability records." />}
      <section className="capability-grid">
        {capabilities.data?.models.map((model, index) => {
          const open = expanded === model.model_id;
          return <motion.article className={`capability-card glass-card lifecycle-${model.status}`} key={model.model_id} layout whileHover={reduced ? undefined : { y: -2 }} transition={{ duration: reduced ? 0 : motionDuration.fast, ease: premiumEase }}>
            <span className="capability-card__index" aria-hidden="true">MODEL / {String(index + 1).padStart(2, "0")}</span>
            <span className="capability-card__orbit" aria-hidden="true"><i /><i /><b /></span>
            <button type="button" aria-expanded={open} onClick={() => setExpanded(open ? null : model.model_id)}>
              <span className="capability-card__icon"><Cpu aria-hidden="true" /></span>
              <span className="capability-card__title"><small>{humanize(model.modality)}</small><code>{model.model_id}</code></span>
              <StatusBadge tone={lifecycleTone(model.status)}>{humanize(model.status)}</StatusBadge>
              {model.runtime_default && <span className="runtime-pill"><Radio aria-hidden="true" /> Runtime default</span>}
              <ChevronDown className={open ? "is-open" : ""} aria-hidden="true" />
            </button>
            <p className="capability-card__scope">{model.validated_scope}</p>
            {model.status === "rejected_experiment" && <p className="capability-card__verdict">Evaluated and not promoted</p>}
            {model.status === "experimental" && <p className="capability-card__verdict">Experimental / bounded scope remains binding</p>}
            <AnimatePresence initial={false}>{open && <motion.div className="capability-card__details" initial={reduced ? false : { opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={reduced ? undefined : { opacity: 0, height: 0 }} transition={{ duration: reduced ? 0 : motionDuration.standard, ease: premiumEase }}><dl><div><dt>Validated scope</dt><dd>{model.validated_scope}</dd></div><div><dt>Confidence semantics</dt><dd>{humanize(model.confidence_semantics)}</dd></div><div><dt>Evaluation reference</dt><dd><code>{model.evaluation_reference}</code></dd></div></dl>{model.status === "rejected_experiment" && <p>Evaluated and not promoted. Preserved as a rejected experimental result; it is not a production capability.</p>}{model.status === "experimental" && <p>Experimental capability. Its validated scope and limitations remain binding.</p>}</motion.div>}</AnimatePresence>
          </motion.article>;
        })}
      </section>
    </PageTransition>
  );
}
