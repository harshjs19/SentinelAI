"""Offline deterministic safety foundation for the future Maintenance Copilot."""

from modules.copilot.context import (
    CopilotContextBuilder,
    CopilotGenerationContext,
    PreparedCopilotRequest,
    generation_context_payload,
)
from modules.copilot.contracts import (
    COPILOT_SCHEMA_VERSION,
    PROMPT_POLICY_VERSION,
    VALIDATOR_POLICY_VERSION,
    CopilotDraft,
    CopilotIntent,
    FallbackReason,
    GenerationStatus,
    MaintenanceCopilotRequest,
    RequestDisposition,
    SafetyViolationCode,
    ValidationResult,
)
from modules.copilot.exceptions import CopilotInputError, CopilotInputErrorCode
from modules.copilot.policy import RequestPolicyDecision, decide_request_policy
from modules.copilot.report import (
    MaintenanceReport,
    assemble_fallback_report,
    assemble_maintenance_report,
    maintenance_report_payload,
    verify_maintenance_report,
    verify_report_digest,
)
from modules.copilot.validation import MaintenanceSafetyValidator

__all__ = [
    "COPILOT_SCHEMA_VERSION",
    "PROMPT_POLICY_VERSION",
    "VALIDATOR_POLICY_VERSION",
    "CopilotContextBuilder",
    "CopilotDraft",
    "CopilotGenerationContext",
    "CopilotInputError",
    "CopilotInputErrorCode",
    "CopilotIntent",
    "FallbackReason",
    "GenerationStatus",
    "MaintenanceCopilotRequest",
    "MaintenanceReport",
    "MaintenanceSafetyValidator",
    "PreparedCopilotRequest",
    "RequestDisposition",
    "RequestPolicyDecision",
    "SafetyViolationCode",
    "ValidationResult",
    "assemble_fallback_report",
    "assemble_maintenance_report",
    "decide_request_policy",
    "generation_context_payload",
    "maintenance_report_payload",
    "verify_maintenance_report",
    "verify_report_digest",
]
