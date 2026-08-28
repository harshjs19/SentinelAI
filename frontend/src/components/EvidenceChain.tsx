import { motion, useReducedMotion } from "framer-motion";
import { BarChart3, Database, FileCheck2, ScanLine, ScrollText } from "lucide-react";

import type { MaintenanceReportEvidence } from "../api/types";
import { usePointerSpotlight } from "../hooks/usePointerSpotlight";
import { formatDate, shortId } from "../lib/format";
import { motionDuration, premiumEase } from "../lib/motion";

const icons = [ScanLine, BarChart3, Database, FileCheck2, ScrollText];

export function EvidenceChain({ evidence }: { evidence: MaintenanceReportEvidence }) {
  const reduced = useReducedMotion();
  const spotlight = usePointerSpotlight<HTMLElement>();
  const source = evidence.sources[0];
  const nodes = [
    {
      label: "Source",
      value: source ? `${source.modality} · ${source.source_kind}` : "Stored provenance",
      detail: source ? shortId(source.sha256) : "No source metadata",
      fullDetail: source?.sha256 ?? "No source digest returned",
    },
    {
      label: "Analysis",
      value: evidence.analysis.condition,
      detail: shortId(evidence.analysis.analysis_id),
      fullDetail: evidence.analysis.analysis_id,
    },
    {
      label: "Evidence Package",
      value: `Schema ${evidence.evidence_package.schema_version}`,
      detail: shortId(evidence.evidence_package.package_id),
      fullDetail: evidence.evidence_package.package_digest_sha256,
    },
    {
      label: "Retrieval Bundle",
      value: evidence.retrieval_bundle.embedding_model_id,
      detail: shortId(evidence.retrieval_bundle.retrieval_bundle_digest_sha256),
      fullDetail: evidence.retrieval_bundle.corpus_digest_sha256,
    },
    {
      label: "Maintenance Report",
      value: evidence.report.generation_status,
      detail: formatDate(evidence.report.generated_at),
      fullDetail: evidence.report.report_digest_sha256,
    },
  ];

  return (
    <section ref={spotlight.ref} onPointerMove={spotlight.onPointerMove} className="evidence-chain glass-card spotlight-surface" aria-labelledby="evidence-chain-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Verified lineage</p>
          <h2 id="evidence-chain-title">Evidence Chain</h2>
        </div>
        <span>Stored historical bindings</span>
      </div>
      <div className="evidence-chain__track">
        <motion.div
          className="evidence-chain__flow"
          initial={reduced ? false : { scale: 0, opacity: 0 }}
          whileInView={{ scale: 1, opacity: 1 }}
          viewport={{ once: true, amount: 0.65 }}
          transition={{ duration: reduced ? 0 : motionDuration.cinematic, ease: premiumEase }}
        />
        <motion.i
          className="evidence-chain__signal evidence-chain__signal--horizontal"
          initial={reduced ? false : { left: "8%", opacity: 0 }}
          whileInView={reduced ? undefined : { left: ["8%", "92%"], opacity: [0, 1, 1, 0] }}
          viewport={{ once: true, amount: 0.65 }}
          transition={{ duration: motionDuration.cinematic, delay: 0.18, ease: premiumEase, times: [0, 0.12, 0.84, 1] }}
        />
        <motion.i
          className="evidence-chain__signal evidence-chain__signal--vertical"
          initial={reduced ? false : { top: "4%", opacity: 0 }}
          whileInView={reduced ? undefined : { top: ["4%", "96%"], opacity: [0, 1, 1, 0] }}
          viewport={{ once: true, amount: 0.45 }}
          transition={{ duration: motionDuration.cinematic, delay: 0.18, ease: premiumEase, times: [0, 0.12, 0.84, 1] }}
        />
        {nodes.map((node, index) => {
          const Icon = icons[index] ?? FileCheck2;
          return (
            <motion.article
              className="evidence-node"
              key={node.label}
              initial={reduced ? false : { opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.65 }}
              transition={{ delay: reduced ? 0 : index * 0.07, duration: reduced ? 0 : motionDuration.enter, ease: premiumEase }}
              tabIndex={0}
            >
              <span className="evidence-node__icon">
                <Icon aria-hidden="true" />
              </span>
              <small>{node.label}</small>
              <strong>{node.value}</strong>
              <code>{node.detail}</code>
              <span className="evidence-node__detail"><code>{node.fullDetail}</code></span>
            </motion.article>
          );
        })}
      </div>
      <p className="evidence-chain__note">
        The chain represents one stored single-modality report. It does not imply sensor fusion.
      </p>
    </section>
  );
}
