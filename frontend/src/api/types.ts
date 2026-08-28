export type Modality = "timeseries" | "audio" | "vision" | "thermal";
export type ConditionState = "normal" | "abnormal" | "indeterminate";
export type AnalysisStatus = "complete" | "provisional" | "insufficient_evidence";
export type ConfidenceKind = "raw" | "calibrated";
export type GenerationStatus = "generated" | "deterministic" | "fallback";
export type FallbackReason =
  | "generation_unavailable"
  | "generation_failed"
  | "validation_failed"
  | "no_grounded_content"
  | "unsupported_request";
export type RequestDisposition =
  | "answered"
  | "partially_answered"
  | "not_supported_by_current_evidence";
export type CopilotIntent =
  | "summarize_analysis"
  | "explain_finding"
  | "explain_confidence"
  | "inspection_considerations"
  | "explain_limitations";
export type ModelLifecycle =
  | "validated_baseline"
  | "experimental"
  | "rejected_experiment";

export interface Machine {
  id: string;
  name: string;
  asset_type: string;
}

export interface ModelCapability {
  model_id: string;
  modality: Modality;
  status: ModelLifecycle;
  runtime_default: boolean;
  validated_scope: string;
  evaluation_reference: string;
  confidence_semantics: string;
}

export interface ModelCapabilitiesResponse {
  models: ModelCapability[];
}

export interface TimeseriesSample {
  ch1_bias: number;
  ch1_derivedPk: number;
  ch1_direct: number;
  ch1_directRMS: number;
  ch1_velocityPk: number;
  ch1_velocityRMS: number;
}

export interface MaintenanceFinding {
  finding_id: string;
  modality: Modality;
  code: string;
  condition: ConditionState;
  confidence: number;
  confidence_kind: ConfidenceKind;
}

export interface NarrativeItem {
  finding_id: string;
  text: string;
  citation_ids: string[];
}

export interface MaintenanceNarrative {
  executive_summary: string;
  finding_explanations: NarrativeItem[];
  inspection_considerations: NarrativeItem[];
  knowledge_gap_statement: string | null;
}

export interface ClaimSupport {
  condition_available: boolean;
  failure_probability_available: boolean;
  fault_severity_available: boolean;
  health_score_available: boolean;
  operational_risk_available: boolean;
}

export interface MaintenanceAnalysis {
  condition: ConditionState;
  status: AnalysisStatus;
  findings: MaintenanceFinding[];
  health_score: number | null;
  risk_level: "low" | "medium" | "high" | "critical" | null;
  claim_support: ClaimSupport;
}

export interface MaintenanceLimitations {
  analysis_limitations: string[];
  model_scope_limitations: string[];
  unavailable_claims: string[];
  generation_limitations: string[];
}

export interface MaintenanceCitation {
  citation_id: string;
  title: string;
  publisher: string;
  section: string;
  fault_code: string;
  asset_type: string;
  matched_intent: string;
  source_lane: "interpretation" | "maintenance";
}

export interface ProducingModel {
  model_id: string;
  modality: Modality;
  status: Exclude<ModelLifecycle, "rejected_experiment">;
  runtime_default_at_execution: boolean;
  validated_scope: string;
  confidence_semantics: string;
}

export interface SafetyValidation {
  valid: boolean;
  violation_codes: string[];
  validator_policy_version: string;
  repair_attempted: boolean;
}

export interface MaintenanceReport {
  report_id: string;
  machine_id: string;
  generated_at: string;
  generation_status: GenerationStatus;
  fallback_reason: FallbackReason | null;
  request_disposition: RequestDisposition;
  request_intent: CopilotIntent;
  analysis: MaintenanceAnalysis;
  narrative: MaintenanceNarrative;
  limitations: MaintenanceLimitations;
  citations: MaintenanceCitation[];
  producing_models: ProducingModel[];
  safety_validation: SafetyValidation;
  disclaimer: string;
}

export interface MaintenanceReportSummary {
  report_id: string;
  machine_id: string;
  generated_at: string;
  generation_status: GenerationStatus;
  condition: ConditionState;
  analysis_status: AnalysisStatus;
  executive_summary: string;
}

export interface SourceProvenance {
  modality: Modality;
  source_kind: "structured" | "file";
  sha256: string;
  size_bytes: number;
  content_type: string;
}

export interface MaintenanceReportEvidence {
  report: {
    report_id: string;
    report_digest_sha256: string;
    schema_version: string;
    generation_status: GenerationStatus;
    generated_at: string;
    evidence_package_id: string;
    evidence_package_digest_sha256: string;
    retrieval_bundle_digest_sha256: string;
  };
  analysis: {
    analysis_id: string;
    machine_id: string;
    condition: ConditionState;
    status: AnalysisStatus;
    created_at: string;
  };
  evidence_package: {
    package_id: string;
    package_digest_sha256: string;
    schema_version: string;
    created_at: string;
    analysis_id: string;
  };
  retrieval_bundle: {
    retrieval_bundle_digest_sha256: string;
    evidence_package_id: string;
    evidence_package_digest_sha256: string;
    corpus_digest_sha256: string;
    embedding_model_id: string;
    embedding_model_revision: string;
    schema_version: string;
  };
  sources: SourceProvenance[];
}

export interface TimeseriesSubmission {
  modality: "timeseries";
  samples: TimeseriesSample[];
  intent: CopilotIntent;
  question?: string;
}

export interface MediaSubmission {
  modality: "audio" | "vision" | "thermal";
  file: File;
  intent: CopilotIntent;
  question?: string;
}

export type MaintenanceSubmission = TimeseriesSubmission | MediaSubmission;

