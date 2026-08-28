import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Check, Clipboard, Database, FileKey2 } from "lucide-react";
import { useState } from "react";

import type { MaintenanceReportEvidence } from "../api/types";
import { formatBytes, formatDate, humanize, shortId } from "../lib/format";
import { motionDuration, premiumEase } from "../lib/motion";

function CopyValue({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const reduced = useReducedMotion();
  const copy = async () => {
    if (!navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  return (
    <button className="copy-value" type="button" onClick={() => void copy()} aria-label={`Copy ${label}`} title={value}>
      <code>{shortId(value, 14, 8)}</code>
      <AnimatePresence initial={false} mode="wait">
        <motion.span
          className="copy-value__icon"
          key={copied ? "copied" : "copy"}
          initial={reduced ? false : { opacity: 0, scale: 0.82 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={reduced ? undefined : { opacity: 0, scale: 0.82 }}
          transition={{ duration: reduced ? 0 : motionDuration.fast, ease: premiumEase }}
        >
          {copied ? <Check aria-hidden="true" /> : <Clipboard aria-hidden="true" />}
        </motion.span>
      </AnimatePresence>
      <span className="sr-only" aria-live="polite">{copied ? `${label} copied` : ""}</span>
    </button>
  );
}

export function EvidencePanel({ evidence }: { evidence: MaintenanceReportEvidence }) {
  return (
    <section className="evidence-panel glass-card" aria-labelledby="evidence-panel-title">
      <div className="section-heading">
        <span className="section-number" aria-hidden="true">05A</span>
        <div>
          <p className="eyebrow">Historical integrity</p>
          <h2 id="evidence-panel-title">Evidence Package</h2>
        </div>
        <FileKey2 aria-hidden="true" />
      </div>

      <div className="evidence-panel__lattice" aria-hidden="true"><i /><i /><i /><span>PACKAGE / VERIFIED BINDINGS</span></div>

      <div className="evidence-panel__identity">
        <div>
          <span>Package ID</span>
          <CopyValue value={evidence.evidence_package.package_id} label="Evidence Package ID" />
        </div>
        <div>
          <span>Package digest</span>
          <CopyValue
            value={evidence.evidence_package.package_digest_sha256}
            label="Evidence Package digest"
          />
        </div>
        <div>
          <span>Analysis binding</span>
          <CopyValue value={evidence.analysis.analysis_id} label="Analysis ID" />
        </div>
      </div>

      <div className="source-provenance-list">
        {evidence.sources.map((source) => (
          <article key={`${source.modality}-${source.sha256}`}>
            <Database aria-hidden="true" />
            <div>
              <strong>{humanize(source.modality)} source provenance</strong>
              <span>
                {humanize(source.source_kind)} · {source.content_type} · {formatBytes(source.size_bytes)}
              </span>
              <CopyValue value={source.sha256} label={`${source.modality} source digest`} />
            </div>
          </article>
        ))}
      </div>

      <dl className="technical-grid">
        <div>
          <dt>Evidence schema</dt>
          <dd>{evidence.evidence_package.schema_version}</dd>
        </div>
        <div>
          <dt>Evidence created</dt>
          <dd>{formatDate(evidence.evidence_package.created_at)}</dd>
        </div>
        <div>
          <dt>Retrieval bundle</dt>
          <dd>
            <CopyValue
              value={evidence.retrieval_bundle.retrieval_bundle_digest_sha256}
              label="Retrieval Bundle digest"
            />
          </dd>
        </div>
        <div>
          <dt>Embedding identity</dt>
          <dd>
            <code>{evidence.retrieval_bundle.embedding_model_id}</code>
            <span>{shortId(evidence.retrieval_bundle.embedding_model_revision)}</span>
          </dd>
        </div>
        <div>
          <dt>Corpus digest</dt>
          <dd>
            <CopyValue value={evidence.retrieval_bundle.corpus_digest_sha256} label="Corpus digest" />
          </dd>
        </div>
      </dl>
      <p className="evidence-panel__note">
        Safe provenance only. Raw source data and retrieval chunks are not returned to the browser.
      </p>
    </section>
  );
}
