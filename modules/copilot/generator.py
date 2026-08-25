from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from modules.copilot.context import CopilotGenerationContext
from modules.copilot.contracts import (
    COPILOT_SCHEMA_VERSION,
    PROMPT_POLICY_VERSION,
    VALIDATOR_POLICY_VERSION,
    CopilotDraft,
    SafetyViolationCode,
)
from modules.copilot.report import GenerationProvenance


class GenerationFailureCode(StrEnum):
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    TRANSIENT = "transient"
    REFUSED = "refused"
    INCOMPLETE = "incomplete"
    MALFORMED_OUTPUT = "malformed_output"
    PROVIDER_ERROR = "provider_error"


_FAILURE_MESSAGES = {
    GenerationFailureCode.CONFIGURATION: "Maintenance generation provider is not configured.",
    GenerationFailureCode.AUTHENTICATION: (
        "Maintenance generation provider authentication failed."
    ),
    GenerationFailureCode.TRANSIENT: "Maintenance generation provider is temporarily unavailable.",
    GenerationFailureCode.REFUSED: "Maintenance generation provider refused the request.",
    GenerationFailureCode.INCOMPLETE: (
        "Maintenance generation provider returned an incomplete response."
    ),
    GenerationFailureCode.MALFORMED_OUTPUT: (
        "Maintenance generation provider returned invalid structured output."
    ),
    GenerationFailureCode.PROVIDER_ERROR: "Maintenance generation provider rejected the request.",
}


class MaintenanceGenerationError(RuntimeError):
    def __init__(self, code: GenerationFailureCode) -> None:
        self.code = code
        super().__init__(_FAILURE_MESSAGES[code])


@dataclass(frozen=True)
class RepairInstruction:
    previous_draft: CopilotDraft
    violation_codes: tuple[SafetyViolationCode, ...]

    def __post_init__(self) -> None:
        if not self.violation_codes:
            raise ValueError("Repair instruction requires at least one violation code")
        if len(set(self.violation_codes)) != len(self.violation_codes):
            raise ValueError("Repair instruction violation codes must be unique")


@dataclass(frozen=True)
class GeneratedDraftResult:
    draft: CopilotDraft
    provider: str
    requested_model: str
    response_model: str | None
    model_snapshot: str | None
    response_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    repair_attempted: bool
    temperature: float | None = None
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.requested_model.strip():
            raise ValueError("Generation provider and requested model cannot be empty")
        for value in (self.input_tokens, self.output_tokens, self.latency_ms):
            if value is not None and (isinstance(value, bool) or value < 0):
                raise ValueError("Generation usage and latency values cannot be negative")

    def to_generation_provenance(self) -> GenerationProvenance:
        return GenerationProvenance(
            provider=self.provider,
            model=self.requested_model,
            model_snapshot=self.model_snapshot,
            temperature=self.temperature,
            reasoning_effort=self.reasoning_effort,
            schema_version=COPILOT_SCHEMA_VERSION,
            prompt_policy_version=PROMPT_POLICY_VERSION,
            validator_policy_version=VALIDATOR_POLICY_VERSION,
            response_id=self.response_id,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            latency_ms=self.latency_ms,
            repair_attempted=self.repair_attempted,
        )


class MaintenanceGenerator(Protocol):
    async def generate(
        self,
        context: CopilotGenerationContext,
        repair: RepairInstruction | None = None,
    ) -> GeneratedDraftResult: ...
