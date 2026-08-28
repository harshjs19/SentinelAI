import type { MaintenanceReport, MaintenanceReportEvidence, ModelCapability } from "../api/types";

export const machine = { id: "11111111-1111-4111-8111-111111111111", name: "Compressor North / Extremely Long Verified Machine Name", asset_type: "rotating_equipment" };

export const capabilities: ModelCapability[] = [
  { model_id: "timeseries_random_forest_utk_v1", modality: "timeseries", status: "validated_baseline", runtime_default: true, validated_scope: "UTK per-recording fault classification", evaluation_reference: "evaluation/timeseries_baseline_results.json", confidence_semantics: "raw_predict_proba" },
  { model_id: "thermal_autoencoder_mvt_v1", modality: "thermal", status: "experimental", runtime_default: true, validated_scope: "Bounded thermal anomaly evidence", evaluation_reference: "evaluation/thermal_baseline_results.json", confidence_semantics: "bounded_empirical_score" },
  { model_id: "audio_ast_rejected_v1", modality: "audio", status: "rejected_experiment", runtime_default: false, validated_scope: "Rejected Audio AST experiment", evaluation_reference: "evaluation/audio_ast_results.json", confidence_semantics: "not_available" },
];

export const report: MaintenanceReport = {
  report_id: "22222222-2222-4222-8222-222222222222",
  machine_id: machine.id,
  generated_at: "2026-08-27T12:30:00Z",
  generation_status: "fallback",
  fallback_reason: "generation_unavailable",
  request_disposition: "not_supported_by_current_evidence",
  request_intent: "inspection_considerations",
  analysis: {
    condition: "abnormal",
    status: "provisional",
    findings: [{ finding_id: "finding-1", modality: "timeseries", code: "bearing_fault", condition: "abnormal", confidence: 0.91, confidence_kind: "raw" }],
    health_score: null,
    risk_level: null,
    claim_support: { condition_available: true, failure_probability_available: false, fault_severity_available: false, health_score_available: false, operational_risk_available: false },
  },
  narrative: {
    executive_summary: "Stored evidence indicates an abnormal time-series classification. No shutdown or continued-operation decision is supported.",
    finding_explanations: [{ finding_id: "finding-1", text: "The classifier assigned the bearing fault label within its validated scope.", citation_ids: ["K1"] }],
    inspection_considerations: [{ finding_id: "finding-1", text: "Qualified personnel may compare the observation with approved inspection procedures and operating context.", citation_ids: ["K1"] }],
    knowledge_gap_statement: "Severity, operational risk, failure probability, and remaining useful life are not available from this evidence.",
  },
  limitations: {
    analysis_limitations: ["uncalibrated_confidence", "single_modality_evidence"],
    model_scope_limitations: ["utk_recording_scope"],
    unavailable_claims: ["fault_severity_unavailable", "risk_context_unavailable"],
    generation_limitations: ["provider_unavailable_deterministic_fallback"],
  },
  citations: [{ citation_id: "K1", title: "Rotating Equipment Inspection Practice With A Very Long Controlled Reference Title", publisher: "SentinelAI curated corpus", section: "Evidence interpretation", fault_code: "bearing_fault", asset_type: "rotating_equipment", matched_intent: "inspection_considerations", source_lane: "maintenance" }],
  producing_models: [{ model_id: "timeseries_random_forest_utk_v1", modality: "timeseries", status: "validated_baseline", runtime_default_at_execution: true, validated_scope: "UTK per-recording fault classification", confidence_semantics: "raw_predict_proba" }],
  safety_validation: { valid: true, violation_codes: [], validator_policy_version: "v1", repair_attempted: false },
  disclaimer: "This evidence-bounded report supports human review and does not replace qualified maintenance judgment.",
};

export const evidence: MaintenanceReportEvidence = {
  report: { report_id: report.report_id, report_digest_sha256: "a".repeat(64), schema_version: "1.0", generation_status: "fallback", generated_at: report.generated_at, evidence_package_id: "package-1", evidence_package_digest_sha256: "b".repeat(64), retrieval_bundle_digest_sha256: "c".repeat(64) },
  analysis: { analysis_id: "analysis-1", machine_id: machine.id, condition: "abnormal", status: "provisional", created_at: "2026-08-27T12:29:50Z" },
  evidence_package: { package_id: "package-1", package_digest_sha256: "b".repeat(64), schema_version: "1.0", created_at: "2026-08-27T12:29:55Z", analysis_id: "analysis-1" },
  retrieval_bundle: { retrieval_bundle_digest_sha256: "c".repeat(64), evidence_package_id: "package-1", evidence_package_digest_sha256: "b".repeat(64), corpus_digest_sha256: "d".repeat(64), embedding_model_id: "sentence-transformers/all-MiniLM-L6-v2", embedding_model_revision: "revision-0123456789", schema_version: "1.0" },
  sources: [{ modality: "timeseries", source_kind: "structured", sha256: "e".repeat(64), size_bytes: 1536, content_type: "application/json" }],
};
