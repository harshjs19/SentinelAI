from dataclasses import replace
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from modules.copilot.context import PreparedCopilotRequest
from modules.copilot.contracts import (
    CopilotDraft,
    FallbackReason,
    RequestDisposition,
    ValidationResult,
)
from modules.copilot.generator import (
    GeneratedDraftResult,
    GenerationFailureCode,
    MaintenanceGenerationError,
    MaintenanceGenerator,
    RepairInstruction,
)
from modules.copilot.report import (
    GenerationProvenance,
    MaintenanceReport,
    assemble_fallback_report,
    assemble_maintenance_report,
    verify_maintenance_report,
)
from modules.copilot.validation import MaintenanceSafetyValidator, violation_codes

COPILOT_WORKFLOW_VERSION = "maintenance_graph_v1"
COPILOT_GRAPH_RECURSION_LIMIT = 8

_UNAVAILABLE_FAILURES = {
    GenerationFailureCode.CONFIGURATION,
    GenerationFailureCode.AUTHENTICATION,
    GenerationFailureCode.TRANSIENT,
}


class CopilotWorkflowError(RuntimeError):
    """Safe internal error for impossible workflow or report-integrity states."""


class CopilotGraphState(TypedDict):
    prepared: PreparedCopilotRequest
    draft: CopilotDraft | None
    generated_result: GeneratedDraftResult | None
    validation_result: ValidationResult | None
    repair_count: int
    fallback_reason: FallbackReason | None
    generation_provenance: GenerationProvenance | None
    final_report: MaintenanceReport | None


def fallback_reason_for_generation_failure(code: GenerationFailureCode) -> FallbackReason:
    if code in _UNAVAILABLE_FAILURES:
        return FallbackReason.GENERATION_UNAVAILABLE
    return FallbackReason.GENERATION_FAILED


def route_after_generation(
    state: CopilotGraphState,
) -> Literal["validate_draft", "fallback_report"]:
    _validate_repair_count(state)
    if state["fallback_reason"] is not None:
        return "fallback_report"
    if state["draft"] is None or state["generated_result"] is None:
        raise CopilotWorkflowError("Generation completed without a structured draft")
    return "validate_draft"


def route_after_validation(
    state: CopilotGraphState,
) -> Literal["finalize_report", "repair_draft", "fallback_report"]:
    _validate_repair_count(state)
    validation = state["validation_result"]
    if validation is None:
        raise CopilotWorkflowError("Validation routing requires a validation result")
    if validation.valid:
        return "finalize_report"
    if state["repair_count"] == 0:
        return "repair_draft"
    return "fallback_report"


def route_after_repair(
    state: CopilotGraphState,
) -> Literal["validate_draft", "fallback_report"]:
    _validate_repair_count(state)
    if state["repair_count"] != 1:
        raise CopilotWorkflowError("Repair node did not consume the single repair budget")
    if state["fallback_reason"] is not None:
        return "fallback_report"
    if state["draft"] is None or state["generated_result"] is None:
        raise CopilotWorkflowError("Repair completed without a structured draft")
    return "validate_draft"


class MaintenanceCopilotWorkflow:
    def __init__(
        self,
        *,
        generator: MaintenanceGenerator,
        validator: MaintenanceSafetyValidator,
    ) -> None:
        self._generator = generator
        self._validator = validator
        self._graph = self._compile()

    async def run(self, prepared: PreparedCopilotRequest) -> MaintenanceReport:
        initial_state = CopilotGraphState(
            prepared=prepared,
            draft=None,
            generated_result=None,
            validation_result=None,
            repair_count=0,
            fallback_reason=None,
            generation_provenance=None,
            final_report=None,
        )
        completed = await self._graph.ainvoke(
            initial_state,
            config={"recursion_limit": COPILOT_GRAPH_RECURSION_LIMIT},
        )
        report = completed.get("final_report")
        if not isinstance(report, MaintenanceReport):
            raise CopilotWorkflowError("Copilot workflow completed without a report")
        return report

    def compiled_node_names(self) -> frozenset[str]:
        return frozenset(self._graph.get_graph().nodes)

    def _compile(self):
        graph = StateGraph(CopilotGraphState)
        graph.add_node("generate_draft", self._generate_draft)
        graph.add_node("validate_draft", self._validate_draft)
        graph.add_node("repair_draft", self._repair_draft)
        graph.add_node("finalize_report", self._finalize_report)
        graph.add_node("fallback_report", self._fallback_report)
        graph.add_edge(START, "generate_draft")
        graph.add_conditional_edges(
            "generate_draft",
            route_after_generation,
            {
                "validate_draft": "validate_draft",
                "fallback_report": "fallback_report",
            },
        )
        graph.add_conditional_edges(
            "validate_draft",
            route_after_validation,
            {
                "finalize_report": "finalize_report",
                "repair_draft": "repair_draft",
                "fallback_report": "fallback_report",
            },
        )
        graph.add_conditional_edges(
            "repair_draft",
            route_after_repair,
            {
                "validate_draft": "validate_draft",
                "fallback_report": "fallback_report",
            },
        )
        graph.add_edge("finalize_report", END)
        graph.add_edge("fallback_report", END)
        return graph.compile(name=COPILOT_WORKFLOW_VERSION)

    async def _generate_draft(self, state: CopilotGraphState) -> dict[str, object]:
        _validate_repair_count(state)
        if state["repair_count"] != 0:
            raise CopilotWorkflowError("Initial generation requires an unused repair budget")
        try:
            result = await self._generator.generate(state["prepared"].context, repair=None)
        except MaintenanceGenerationError as error:
            return {
                "fallback_reason": fallback_reason_for_generation_failure(error.code),
                "draft": None,
                "generated_result": None,
                "validation_result": None,
                "generation_provenance": None,
            }
        if result.repair_attempted:
            raise CopilotWorkflowError("Initial generation was incorrectly marked as a repair")
        return {
            "draft": result.draft,
            "generated_result": result,
            "validation_result": None,
            "fallback_reason": None,
            "generation_provenance": result.to_generation_provenance(),
        }

    def _validate_draft(self, state: CopilotGraphState) -> dict[str, object]:
        _validate_repair_count(state)
        draft = state["draft"]
        if draft is None:
            raise CopilotWorkflowError("Draft validation requires a structured draft")
        return {"validation_result": self._validator.validate(draft, state["prepared"])}

    async def _repair_draft(self, state: CopilotGraphState) -> dict[str, object]:
        _validate_repair_count(state)
        if state["repair_count"] != 0:
            raise CopilotWorkflowError("Copilot repair budget is exhausted")
        draft = state["draft"]
        validation = state["validation_result"]
        if draft is None or validation is None or validation.valid:
            raise CopilotWorkflowError("Repair requires one rejected structured draft")
        repair = RepairInstruction(draft, violation_codes(validation))
        try:
            result = await self._generator.generate(state["prepared"].context, repair=repair)
        except MaintenanceGenerationError as error:
            provenance = state["generation_provenance"]
            if provenance is not None:
                provenance = replace(provenance, repair_attempted=True)
            return {
                "repair_count": 1,
                "fallback_reason": fallback_reason_for_generation_failure(error.code),
                "draft": None,
                "generated_result": None,
                "generation_provenance": provenance,
            }
        if not result.repair_attempted:
            raise CopilotWorkflowError("Repair generation did not mark the repair attempt")
        return {
            "repair_count": 1,
            "draft": result.draft,
            "generated_result": result,
            "validation_result": None,
            "fallback_reason": None,
            "generation_provenance": result.to_generation_provenance(),
        }

    def _finalize_report(self, state: CopilotGraphState) -> dict[str, object]:
        _validate_repair_count(state)
        draft = state["draft"]
        validation = state["validation_result"]
        provenance = state["generation_provenance"]
        if draft is None or validation is None or not validation.valid or provenance is None:
            raise CopilotWorkflowError("Only a validated draft can be finalized")
        disposition = (
            RequestDisposition.PARTIALLY_ANSWERED
            if draft.knowledge_gap_statement
            else RequestDisposition.ANSWERED
        )
        report = assemble_maintenance_report(
            state["prepared"],
            draft,
            provenance,
            validation,
            request_disposition=disposition,
        )
        _verify_report(report, state["prepared"])
        return {"final_report": report}

    def _fallback_report(self, state: CopilotGraphState) -> dict[str, object]:
        _validate_repair_count(state)
        reason = state["fallback_reason"] or FallbackReason.VALIDATION_FAILED
        report = assemble_fallback_report(
            state["prepared"],
            reason,
            generation_provenance=state["generation_provenance"],
            request_disposition=RequestDisposition.PARTIALLY_ANSWERED,
            validation=state["validation_result"],
        )
        _verify_report(report, state["prepared"])
        return {
            "draft": None,
            "generated_result": None,
            "final_report": report,
        }


def _validate_repair_count(state: CopilotGraphState) -> None:
    count = state["repair_count"]
    if isinstance(count, bool) or count not in (0, 1):
        raise CopilotWorkflowError("Copilot repair count is outside the bounded workflow")


def _verify_report(report: MaintenanceReport, prepared: PreparedCopilotRequest) -> None:
    if not verify_maintenance_report(report, prepared):
        raise CopilotWorkflowError("Maintenance report invariant verification failed")
