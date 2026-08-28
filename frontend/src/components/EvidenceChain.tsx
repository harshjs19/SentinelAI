import { motion, useReducedMotion } from "framer-motion";
import { BarChart3, Database, FileCheck2, ScanLine, ScrollText } from "lucide-react";

import type { MaintenanceReportEvidence } from "../api/types";
import { formatDate, shortId } from "../lib/format";

const icons = [ScanLine, BarChart3, Database, FileCheck2, ScrollText];

export function EvidenceChain({ evidence }: { evidence: MaintenanceReportEvidence }) {
  const reduced = useReducedMotion();
  const source = evidence.sources[0];
  const nodes = [
    {
      label: "Source",
      value: source ? `${source.modality} · ${source.source_kind}` : "Stored provenance",
      detail: source ? shortId(source.sha256) : "No source metadata",
    },
    {
      label: "Analysis",
      value: evidence.analysis.condition,
      detail: shortId(evidence.analysis.analysis_id),
    },
    {
      label: "Evidence Package",
      value: `Schema ${evidence.evidence_package.schema_version}`,
      detail: shortId(evidence.evidence_package.package_id),
    },
    {
      label: "Retrieval Bundle",
      value: evidence.retrieval_bundle.embedding_model_id,
      detail: shortId(evidence.retrieval_bundle.retrieval_bundle_digest_sha256),
    },
    {
      label: "Maintenance Report",
      value: evidence.report.generation_status,
      detail: formatDate(evidence.report.generated_at),
    },
  ];

  return (
    <section className="evidence-chain glass-card" aria-labelledby="evidence-chain-title">
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
          initial={reduced ? false : { scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: reduced ? 0 : 0.8, ease: "easeOut" }}
        />
        {nodes.map((node, index) => {
          const Icon = icons[index] ?? FileCheck2;
          return (
            <motion.article
              className="evidence-node"
              key={node.label}
              initial={reduced ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: reduced ? 0 : index * 0.08, duration: 0.3 }}
              tabIndex={0}
            >
              <span className="evidence-node__icon">
                <Icon aria-hidden="true" />
              </span>
              <small>{node.label}</small>
              <strong>{node.value}</strong>
              <code>{node.detail}</code>
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
