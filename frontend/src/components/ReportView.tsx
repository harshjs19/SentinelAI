import {
  AlertOctagon,
  BookMarked,
  CheckCircle2,
  Gauge,
  Microscope,
  ShieldAlert,
} from "lucide-react";

import type { MaintenanceReport, MaintenanceReportEvidence } from "../api/types";
import { confidenceLabel, formatDate, humanize, limitationLabel } from "../lib/format";
import { CitationCard } from "./CitationCard";
import { EvidenceChain } from "./EvidenceChain";
import { EvidencePanel } from "./EvidencePanel";
import { ProvenancePanel } from "./ProvenancePanel";
import { StatusBadge } from "./StatusBadge";
import { conditionTone } from "./badgeTone";

function TruthMetric({ label, value }: { label: string; value: string }) {
  return <div className="truth-metric"><span>{label}</span><strong>{value}</strong></div>;
}

export function ReportView({ report, evidence }: { report: MaintenanceReport; evidence: MaintenanceReportEvidence | null }) {
  const support = report.analysis.claim_support;
  const allLimitations = [
    ...report.limitations.analysis_limitations,
    ...report.limitations.model_scope_limitations,
    ...report.limitations.unavailable_claims,
    ...report.limitations.generation_limitations,
  ];

  return (
    <div className="report-view">
      <section className={`report-hero glass-panel condition-${report.analysis.condition}`}>
        <div className="report-hero__condition">
          <p className="eyebrow">Authoritative condition</p>
          <h1>{humanize(report.analysis.condition)}</h1>
          <span>{humanize(report.analysis.status)} analysis</span>
        </div>
        <div className="report-hero__summary">
          <div className="report-hero__meta">
            <StatusBadge tone={report.generation_status === "fallback" ? "warning" : "accent"}>
              {humanize(report.generation_status)} report
            </StatusBadge>
            <span>{formatDate(report.generated_at)}</span>
          </div>
          <h2>Executive summary</h2>
          <p>{report.narrative.executive_summary}</p>
          {report.request_disposition !== "answered" && (
            <div className="safe-boundary"><ShieldAlert aria-hidden="true" /><span>{humanize(report.request_disposition)}. The interface adds no operational advice.</span></div>
          )}
        </div>
      </section>

      <section className="truth-grid" aria-label="Scientific claim availability">
        <TruthMetric label="Health" value={support.health_score_available && report.analysis.health_score !== null ? String(report.analysis.health_score) : "Not determined"} />
        <TruthMetric label="Operational risk" value={support.operational_risk_available && report.analysis.risk_level ? humanize(report.analysis.risk_level) : "Not determined"} />
        <TruthMetric label="Failure probability" value={support.failure_probability_available ? "Available in report" : "Not estimated"} />
        <TruthMetric label="Fault severity" value={support.fault_severity_available ? "Available in report" : "Not determined"} />
        <TruthMetric label="Remaining useful life" value="Not estimated" />
      </section>

      <section className="report-section" aria-labelledby="findings-title">
        <div className="section-heading"><div><p className="eyebrow">Bounded model output</p><h2 id="findings-title">Findings</h2></div><Gauge aria-hidden="true" /></div>
        <div className="finding-grid">
          {report.analysis.findings.map((finding) => {
            const narrative = report.narrative.finding_explanations.find((item) => item.finding_id === finding.finding_id);
            return (
              <article className="finding-card glass-card" key={finding.finding_id}>
                <header>
                  <div><span>{humanize(finding.modality)}</span><code>{finding.code}</code></div>
                  <StatusBadge tone={conditionTone(finding.condition)}>{humanize(finding.condition)}</StatusBadge>
                </header>
                <div className="confidence-block">
                  <div><span>Model confidence</span><strong>{confidenceLabel(finding.confidence)}</strong></div>
                  <div className="confidence-track" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(1, finding.confidence)) * 100}%` }} /></div>
                  <p>{humanize(finding.confidence_kind)} confidence</p>
                  {finding.confidence_kind === "raw" && <small>Raw model confidence — not failure probability.</small>}
                </div>
                {narrative && <p className="finding-card__narrative">{narrative.text}</p>}
              </article>
            );
          })}
        </div>
      </section>

      <section className="report-section inspection-section glass-panel" aria-labelledby="inspection-title">
        <div className="section-heading"><div><p className="eyebrow">Non-directive evidence review</p><h2 id="inspection-title">Inspection Considerations</h2></div><Microscope aria-hidden="true" /></div>
        {report.narrative.inspection_considerations.length > 0 ? (
          <ol>{report.narrative.inspection_considerations.map((item) => <li key={item.finding_id}>{item.text}</li>)}</ol>
        ) : <p>No inspection considerations were supported by the current evidence.</p>}
      </section>

      {evidence && <EvidenceChain evidence={evidence} />}
      <div className="report-two-column">{evidence && <EvidencePanel evidence={evidence} />}<ProvenancePanel models={report.producing_models} /></div>

      <section className="report-section" aria-labelledby="citations-title">
        <div className="section-heading"><div><p className="eyebrow">Grounding references</p><h2 id="citations-title">Citations</h2></div><BookMarked aria-hidden="true" /></div>
        {report.citations.length > 0 ? <div className="citation-grid">{report.citations.map((citation) => <CitationCard citation={citation} key={citation.citation_id} />)}</div> : <p className="subdued-copy">No citations were attached to this stored report.</p>}
        <p className="citation-disclaimer">Citation compatibility is checked automatically; semantic support remains subject to human review.</p>
      </section>

      <section className="boundaries glass-panel" aria-labelledby="boundaries-title">
        <div className="section-heading"><div><p className="eyebrow">Scientific boundaries</p><h2 id="boundaries-title">What this report does not claim</h2></div><AlertOctagon aria-hidden="true" /></div>
        <div className="boundary-tags">{allLimitations.map((limitation) => <span key={limitation}>{limitationLabel(limitation)}</span>)}</div>
        {report.narrative.knowledge_gap_statement && <p>{report.narrative.knowledge_gap_statement}</p>}
        <div className="safety-strip"><CheckCircle2 aria-hidden="true" /><div><strong>Safety validation {report.safety_validation.valid ? "passed" : "not confirmed"}</strong><span>Policy {report.safety_validation.validator_policy_version}</span></div></div>
        <p className="report-disclaimer">{report.disclaimer}</p>
      </section>
    </div>
  );
}
