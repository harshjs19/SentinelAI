from domain.enums.analysis_status import AnalysisStatus
from modules.copilot.context import CopilotContextBuilder, PreparedCopilotRequest
from modules.copilot.contracts import (
    CopilotIntent,
    FallbackReason,
    MaintenanceCopilotRequest,
    RequestDisposition,
)
from modules.copilot.generator import MaintenanceGenerator
from modules.copilot.graph import CopilotWorkflowError, MaintenanceCopilotWorkflow
from modules.copilot.policy import RequestPolicyDecision, decide_request_policy
from modules.copilot.report import (
    MaintenanceReport,
    assemble_deterministic_report,
    assemble_fallback_report,
    verify_maintenance_report,
)
from modules.copilot.validation import MaintenanceSafetyValidator

_DETERMINISTIC_INTENTS = {
    CopilotIntent.EXPLAIN_CONFIDENCE,
    CopilotIntent.EXPLAIN_LIMITATIONS,
}


class MaintenanceCopilotService:
    def __init__(
        self,
        *,
        generator: MaintenanceGenerator | None,
        validator: MaintenanceSafetyValidator,
        context_builder: CopilotContextBuilder | None = None,
    ) -> None:
        self._context_builder = context_builder or CopilotContextBuilder()
        self._workflow = (
            MaintenanceCopilotWorkflow(generator=generator, validator=validator)
            if generator is not None
            else None
        )

    async def generate_report(self, request: MaintenanceCopilotRequest) -> MaintenanceReport:
        prepared = self._context_builder.build(request)
        decision = decide_request_policy(prepared)
        if not decision.provider_required:
            return self._deterministic_path(prepared, decision)
        if self._workflow is None:
            return self._verified_fallback(
                prepared,
                FallbackReason.GENERATION_UNAVAILABLE,
                RequestDisposition.PARTIALLY_ANSWERED,
            )
        report = await self._workflow.run(prepared)
        self._verify(report, prepared)
        return report

    def _deterministic_path(
        self,
        prepared: PreparedCopilotRequest,
        decision: RequestPolicyDecision,
    ) -> MaintenanceReport:
        if (
            prepared.request.intent in _DETERMINISTIC_INTENTS
            and decision.fallback_reason is None
            and decision.deterministic_explanations
        ):
            report = assemble_deterministic_report(
                prepared,
                decision.deterministic_explanations,
                request_disposition=decision.disposition,
            )
            self._verify(report, prepared)
            return report
        reason = decision.fallback_reason
        if reason is None:
            raise CopilotWorkflowError("Deterministic policy returned no report outcome")
        return self._verified_fallback(
            prepared,
            reason,
            _fallback_disposition(prepared, decision),
        )

    def _verified_fallback(
        self,
        prepared: PreparedCopilotRequest,
        reason: FallbackReason,
        disposition: RequestDisposition,
    ) -> MaintenanceReport:
        report = assemble_fallback_report(
            prepared,
            reason,
            request_disposition=disposition,
        )
        self._verify(report, prepared)
        return report

    @staticmethod
    def _verify(report: MaintenanceReport, prepared: PreparedCopilotRequest) -> None:
        if not verify_maintenance_report(report, prepared):
            raise CopilotWorkflowError("Maintenance report invariant verification failed")


def _fallback_disposition(
    prepared: PreparedCopilotRequest,
    decision: RequestPolicyDecision,
) -> RequestDisposition:
    if decision.fallback_reason is FallbackReason.UNSUPPORTED_REQUEST:
        return RequestDisposition.NOT_SUPPORTED_BY_CURRENT_EVIDENCE
    if (
        prepared.context.analysis_status is AnalysisStatus.INSUFFICIENT_EVIDENCE
        or not prepared.context.claim_support.condition_available
    ):
        return RequestDisposition.NOT_SUPPORTED_BY_CURRENT_EVIDENCE
    return RequestDisposition.PARTIALLY_ANSWERED
