import {
  AlertOctagon,
  BookMarked,
  CheckCircle2,
  Gauge,
  Microscope,
  ShieldAlert,
} from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";

import type { MaintenanceReport, MaintenanceReportEvidence } from "../api/types";
import { confidenceLabel, formatDate, humanize, limitationLabel, shortId } from "../lib/format";
import { motionDuration, premiumEase } from "../lib/motion";
import { CitationCard } from "./CitationCard";
import { EvidenceChain } from "./EvidenceChain";
import { EvidencePanel } from "./EvidencePanel";
import { ProvenancePanel } from "./ProvenancePanel";
import { SignatureHero } from "./SignatureHero";
import { StatusBadge } from "./StatusBadge";
import { conditionTone } from "./badgeTone";

export function ReportView({ report, evidence }: { report: MaintenanceReport; evidence: MaintenanceReportEvidence | null }) {
  const reduced = useReducedMotion();
  const support = report.analysis.claim_support;
  const allLimitations = [
    ...report.limitations.analysis_limitations,
    ...report.limitations.model_scope_limitations,
    ...report.limitations.unavailable_claims,
    ...report.limitations.generation_limitations,
  ];
  const unavailableClaims = [
    !support.failure_probability_available && "Failure probability was not inferred from the current evidence.",
    !support.fault_severity_available && "Fault severity was not inferred from the current evidence.",
    !(support.health_score_available && report.analysis.health_score !== null) && "Machine health was not inferred from the current evidence.",
    !(support.operational_risk_available && report.analysis.risk_level) && "Operational risk was not inferred from the current evidence.",
    "Remaining useful life is not produced by this report schema.",
  ].filter((claim): claim is string => Boolean(claim));
  const reportSceneItems = evidence ? [
    { label: "Source", meta: evidence.sources[0] ? humanize(evidence.sources[0].modality) : "stored provenance", tone: "accent" as const },
    { label: "Analysis", meta: humanize(evidence.analysis.status), tone: report.analysis.condition === "normal" ? "positive" as const : "warning" as const },
    { label: "Evidence Package", meta: `schema ${evidence.evidence_package.schema_version}`, tone: "accent" as const },
    { label: "Retrieval Bundle", meta: `schema ${evidence.retrieval_bundle.schema_version}`, tone: "neutral" as const },
    { label: "Maintenance Report", meta: humanize(evidence.report.generation_status), tone: "positive" as const },
  ] : [
    { label: "Stored analysis", meta: humanize(report.analysis.status), tone: "neutral" as const },
  ];

  return (
    <div className="report-view">
      <SignatureHero
        index="ARTIFACT / 05"
        eyebrow="Maintenance report / technical intelligence brief"
        title={<>{humanize(report.analysis.condition)} <em>Evidence Brief</em></>}
        description="A stored, evidence-bounded maintenance artifact for qualified human review. Condition is model output; it is not severity, health, operational risk, failure probability, or remaining useful life."
        variant="report"
        sceneKicker="Verified artifact architecture"
        sceneTitle={`Report ${shortId(report.report_id, 8, 6)}`}
        sceneNote={evidence ? "Historical lineage is loaded from the stored evidence endpoint without recomputation." : "Stored report loaded; evidence metadata is not available in this view."}
        sceneItems={reportSceneItems}
        facts={
          <>
            <span><strong>Machine</strong><code>{shortId(report.machine_id, 10, 6)}</code></span>
            <span><strong>Report generated</strong><time dateTime={report.generated_at} title={report.generated_at}>{formatDate(report.generated_at)}</time></span>
            {report.producing_models[0] && <span><strong>Producing model</strong><code>{report.producing_models[0].model_id}</code></span>}
          </>
        }
        sceneFooter={<StatusBadge tone={report.generation_status === "fallback" ? "warning" : "accent"}>{humanize(report.generation_status)} report</StatusBadge>}
      />

      <section className="report-executive glass-panel" aria-labelledby="executive-title">
        <div className="report-executive__number" aria-hidden="true">01</div>
        <div className="section-heading">
          <div><p className="eyebrow">Executive intelligence</p><h2 id="executive-title">Evidence-bounded summary</h2></div>
          <StatusBadge tone={conditionTone(report.analysis.condition)}>{humanize(report.analysis.condition)}</StatusBadge>
        </div>
        <p className="executive-summary">{report.narrative.executive_summary}</p>
        {report.request_disposition !== "answered" && (
          <div className="safe-boundary"><ShieldAlert aria-hidden="true" /><span>{humanize(report.request_disposition)}. The interface adds no operational advice.</span></div>
        )}
      </section>

      <section className="report-section" aria-labelledby="findings-title">
        <div className="section-heading report-section__heading"><span className="section-number" aria-hidden="true">02</span><div><p className="eyebrow">Bounded model output</p><h2 id="findings-title">Finding Intelligence</h2></div><Gauge aria-hidden="true" /></div>
        <div className="finding-grid">
          {report.analysis.findings.map((finding) => {
            const narrative = report.narrative.finding_explanations.find((item) => item.finding_id === finding.finding_id);
            return (
              <article className="finding-card glass-card" key={finding.finding_id}>
                <header>
                  <div><span>{humanize(finding.modality)}</span><code>{finding.code}</code></div>
                  <StatusBadge tone={conditionTone(finding.condition)}>{humanize(finding.condition)}</StatusBadge>
                </header>
                <div className="confidence-block" title="Classifier confidence for this prediction. It is not a failure probability, severity score, health score, operational risk estimate, or remaining useful life estimate.">
                  <div><span>Model confidence</span><strong>{confidenceLabel(finding.confidence)}</strong></div>
                  <div className="confidence-track" aria-hidden="true"><motion.i initial={reduced ? false : { width: 0 }} whileInView={{ width: `${Math.max(0, Math.min(1, finding.confidence)) * 100}%` }} viewport={{ once: true, amount: 0.8 }} transition={{ duration: reduced ? 0 : motionDuration.cinematic, ease: premiumEase }} /></div>
                  <p>{finding.confidence_kind === "raw" ? "Raw / uncalibrated classifier confidence" : "Calibrated classifier confidence"}</p>
                  <small>Not failure probability, fault severity, machine health, operational risk, or remaining useful life.</small>
                </div>
                {narrative && <p className="finding-card__narrative">{narrative.text}</p>}
              </article>
            );
          })}
        </div>
      </section>

      <section className="scientific-claims glass-panel" aria-labelledby="claim-boundaries-title">
        <div className="section-heading report-section__heading"><span className="section-number" aria-hidden="true">03</span><div><p className="eyebrow">Trust boundaries</p><h2 id="claim-boundaries-title">Scientific Boundaries</h2></div><ShieldAlert aria-hidden="true" /></div>
        <p className="scientific-claims__intro">SentinelAI preserves unsupported claims as explicit boundaries and does not convert classifier confidence into operational certainty.</p>
        <ul className="claim-boundary-list" aria-label="Scientific claim boundaries">
          {unavailableClaims.map((claim) => <li key={claim}>{claim}</li>)}
        </ul>
      </section>

      {evidence && <EvidenceChain evidence={evidence} />}
      <div className="report-two-column">{evidence && <EvidencePanel evidence={evidence} />}<ProvenancePanel models={report.producing_models} /></div>

      <section className="report-section inspection-section glass-panel" aria-labelledby="inspection-title">
        <div className="section-heading report-section__heading"><span className="section-number" aria-hidden="true">06</span><div><p className="eyebrow">Non-directive evidence review</p><h2 id="inspection-title">Inspection Considerations</h2></div><Microscope aria-hidden="true" /></div>
        <p className="inspection-section__boundary">Considerations support qualified review; they are not commands, urgency ratings, or authorization to operate or stop equipment.</p>
        {report.narrative.inspection_considerations.length > 0 ? (
          <ol>{report.narrative.inspection_considerations.map((item) => <li key={item.finding_id}>{item.text}</li>)}</ol>
        ) : <p>No inspection considerations were supported by the current evidence.</p>}
      </section>

      <section className="report-section" aria-labelledby="citations-title">
        <div className="section-heading report-section__heading"><span className="section-number" aria-hidden="true">07</span><div><p className="eyebrow">Grounding references</p><h2 id="citations-title">Knowledge Evidence</h2></div><BookMarked aria-hidden="true" /></div>
        {report.citations.length > 0 ? <div className="citation-grid">{report.citations.map((citation) => <CitationCard citation={citation} key={citation.citation_id} />)}</div> : <p className="subdued-copy">No citations were attached to this stored report.</p>}
        <p className="citation-disclaimer">Citation compatibility is checked automatically; semantic support remains subject to human review.</p>
      </section>

      <section className="boundaries glass-panel" aria-labelledby="boundaries-title">
        <div className="section-heading report-section__heading"><span className="section-number" aria-hidden="true">08</span><div><p className="eyebrow">Binding limitations</p><h2 id="boundaries-title">What this report does not claim</h2></div><AlertOctagon aria-hidden="true" /></div>
        <div className="boundary-tags">{allLimitations.map((limitation, index) => <motion.span key={limitation} initial={reduced ? false : { opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? 0 : motionDuration.standard, delay: reduced ? 0 : Math.min(index * 0.04, 0.2), ease: premiumEase }}>{limitationLabel(limitation)}</motion.span>)}</div>
        {report.narrative.knowledge_gap_statement && <p>{report.narrative.knowledge_gap_statement}</p>}
        <div className="safety-strip"><CheckCircle2 aria-hidden="true" /><div><strong>Safety validation {report.safety_validation.valid ? "passed" : "not confirmed"}</strong><span>Policy {report.safety_validation.validator_policy_version}</span></div></div>
        <p className="report-disclaimer">{report.disclaimer}</p>
      </section>
    </div>
  );
}
