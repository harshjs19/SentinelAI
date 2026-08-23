from enum import StrEnum


class AnalysisLimitation(StrEnum):
    UNCALIBRATED_CONFIDENCE = "uncalibrated_confidence"
    FAULT_SEVERITY_UNAVAILABLE = "fault_severity_unavailable"
    RISK_CONTEXT_UNAVAILABLE = "risk_context_unavailable"
    SINGLE_MODALITY_EVIDENCE = "single_modality_evidence"
