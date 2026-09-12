import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronDown, Cpu, Radio } from "lucide-react";
import { useCallback, useState } from "react";

import { listModelCapabilities } from "../api/capabilities";
import { listModelEvaluationSummaries, type ModelEvaluationSummary } from "../api/evaluations";
import type { ModelCapability } from "../api/types";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { PageTransition } from "../components/PageTransition";
import { SignatureHero } from "../components/SignatureHero";
import { lifecycleTone } from "../components/badgeTone";
import { StatusBadge } from "../components/StatusBadge";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { humanize, shortId } from "../lib/format";
import { motionDuration, premiumEase } from "../lib/motion";

export function ModelsPage() {
  const reduced = useReducedMotion();
  const [expanded, setExpanded] = useState<string | null>(null);
  const loader = useCallback(async (signal: AbortSignal) => {
    const [capabilities, evaluations] = await Promise.all([
      listModelCapabilities(signal),
      listModelEvaluationSummaries(signal),
    ]);
    const evaluationByModel = new Map(evaluations.map((item) => [item.model_id, item]));
    const models = capabilities.models.map((model) => {
      const evaluation = evaluationByModel.get(model.model_id);
      if (!evaluation || evaluation.evaluation_reference !== model.evaluation_reference) {
        throw new Error("Model evaluation bindings are incomplete.");
      }
      return { model, evaluation };
    });
    return { models };
  }, []);
  const capabilities = useAsyncResource(loader);

  return (
    <PageTransition>
      <SignatureHero
        index="CHAPTER / 06"
        eyebrow="Model capabilities / transparent governance"
        title={<>Model <em>Capabilities</em></>}
        description="Review declared lifecycle state, validated scope, confidence semantics, and verified evaluation evidence without hiding experimental or rejected results."
        variant="models"
        sceneKicker="Capability constellation"
        sceneTitle={capabilities.data ? `${capabilities.data.models.length} declared model records` : "Authoritative capability registry"}
        sceneNote="Spatial grouping communicates lifecycle identity only; it does not imply model fusion, ensemble execution, or live inference."
        sceneItems={(capabilities.data?.models ?? []).map(({ model }) => ({
          label: humanize(model.modality),
          meta: `Lifecycle / ${humanize(model.status)}`,
          tone: model.status === "validated_baseline" ? "positive" : model.status === "experimental" ? "warning" : "danger",
        }))}
        facts={capabilities.data &&
          <>
            <span><strong>{capabilities.data.models.filter(({ model }) => model.runtime_default).length}</strong> runtime-default declarations</span>
            <span><strong>Lifecycle transparent</strong> rejected results stay visible</span>
          </>
        }
      />
      {capabilities.loading && <LoadingState label="Loading authoritative capability registry…" />}
      {capabilities.error && <ErrorState error={capabilities.error} onRetry={capabilities.reload} />}
      {capabilities.data?.models.length === 0 && <EmptyState title="No registered capabilities" message="The capability registry contains no model records." />}
      <section className="capability-grid">
        {capabilities.data?.models.map(({ model, evaluation }, index) => {
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
            <div className="model-evaluation" aria-label={`Verified evaluation for ${model.model_id}`}>
              <span>{evaluation.metric_label}</span>
              <strong>{formatEvaluationScore(evaluation)}</strong>
              <small>{evaluation.known_limitation}</small>
            </div>
            {model.status === "rejected_experiment" && <p className="capability-card__verdict">Evaluated and not promoted</p>}
            {model.status === "experimental" && <p className="capability-card__verdict">Experimental / bounded scope remains binding</p>}
            <AnimatePresence initial={false}>{open && <ModelDetails model={model} evaluation={evaluation} reduced={Boolean(reduced)} />}</AnimatePresence>
          </motion.article>;
        })}
      </section>
    </PageTransition>
  );
}

function formatEvaluationScore(evaluation: ModelEvaluationSummary): string {
  return `${(evaluation.metric_value * 100).toFixed(1)}%`;
}

function ModelDetails({ model, evaluation, reduced }: { model: ModelCapability; evaluation: ModelEvaluationSummary; reduced: boolean }) {
  return (
    <motion.div className="capability-card__details" initial={reduced ? false : { opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={reduced ? undefined : { opacity: 0, height: 0 }} transition={{ duration: reduced ? 0 : motionDuration.standard, ease: premiumEase }}>
      <dl>
        <div><dt>Validated scope</dt><dd>{model.validated_scope}</dd></div>
        <div><dt>Confidence semantics</dt><dd>{humanize(model.confidence_semantics)}</dd></div>
        <div><dt>Evaluation reference</dt><dd><code>{model.evaluation_reference}</code></dd></div>
        <div><dt>Evaluation source digest</dt><dd><code title={evaluation.source_digest_sha256}>{shortId(evaluation.source_digest_sha256, 14, 8)}</code></dd></div>
      </dl>
      {model.status === "rejected_experiment" && <p>Evaluated and not promoted. Preserved as a rejected experimental result; it is not a production capability.</p>}
      {model.status === "experimental" && <p>Experimental capability. Its validated scope and limitations remain binding.</p>}
    </motion.div>
  );
}
