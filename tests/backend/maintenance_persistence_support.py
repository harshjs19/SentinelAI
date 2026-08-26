from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from ai_core.model_capabilities import get_runtime_default_capability
from ai_core.model_provenance import snapshot_producing_model_context
from backend.app.services.evidence_package_service import EvidencePackageService
from backend.app.services.maintenance_workflow_service import MaintenanceWorkflowResult
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.result import InferenceResult
from modules.copilot.context import CopilotContextBuilder
from modules.copilot.contracts import (
    CopilotIntent,
    FallbackReason,
    MaintenanceCopilotRequest,
    ValidationResult,
)
from modules.copilot.report import (
    MaintenanceReport,
    assemble_deterministic_report,
    assemble_fallback_report,
    assemble_maintenance_report,
)
from modules.decision.engine import DecisionEngine
from shared.evidence.provenance import file_source_provenance
from tests.copilot.support import (
    ChunkSpec,
    generated_result,
    make_bundle,
    make_valid_draft,
)


def make_vision_workflow_result(
    *,
    machine_id: UUID | None = None,
    report_id: UUID | None = None,
    generated_at: datetime | None = None,
    generated: bool = False,
    fallback: bool = False,
) -> tuple[Machine, MaintenanceWorkflowResult]:
    machine = Machine(machine_id or uuid4(), "Persistence fixture", "pcb1")
    prediction = Prediction(Modality.VISION, "visual_anomaly", 0.91)
    model_context = snapshot_producing_model_context(
        get_runtime_default_capability(Modality.VISION)
    )
    inference_result = InferenceResult(prediction, model_context)
    analysis = DecisionEngine().evaluate(machine.id, (prediction,))
    package = EvidencePackageService().build(
        machine,
        analysis,
        (file_source_provenance(Modality.VISION, b"private fixture bytes", "image/png"),),
        producing_models=(model_context,),
    )
    bundle = make_bundle(
        package,
        (
            ChunkSpec(
                "visual_anomaly",
                asset_type=machine.asset_type,
                text="Synthetic source-backed visual inspection context.",
            ),
        ),
    )
    prepared = CopilotContextBuilder().build(
        MaintenanceCopilotRequest(
            evidence_package=package,
            retrieval_bundle=bundle,
            intent=CopilotIntent.EXPLAIN_FINDING,
        )
    )
    report_time = generated_at or datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
    if generated and fallback:
        raise ValueError("A fixture report cannot be both generated and fallback")
    if generated:
        report = assemble_maintenance_report(
            prepared,
            make_valid_draft(
                summary="The analysis reported a visual anomaly.",
                finding_text="The cited source provides visual inspection context.",
            ),
            generated_result(make_valid_draft()).to_generation_provenance(),
            ValidationResult(valid=True, violations=()),
            report_id=report_id,
            generated_at=report_time,
        )
    elif fallback:
        report = assemble_fallback_report(
            prepared,
            FallbackReason.GENERATION_UNAVAILABLE,
            report_id=report_id,
            generated_at=report_time,
        )
    else:
        report = assemble_deterministic_report(
            prepared,
            ("The analysis reported a visual anomaly.",),
            report_id=report_id,
            generated_at=report_time,
        )
    return machine, MaintenanceWorkflowResult(
        inference_result=inference_result,
        analysis=analysis,
        evidence_package=package,
        retrieval_bundle=bundle,
        maintenance_report=report,
    )


def replace_report(
    result: MaintenanceWorkflowResult,
    *,
    report_id: UUID,
    generated_at: datetime,
) -> MaintenanceWorkflowResult:
    prepared = CopilotContextBuilder().build(
        MaintenanceCopilotRequest(
            evidence_package=result.evidence_package,
            retrieval_bundle=result.retrieval_bundle,
            intent=result.maintenance_report.request_intent,
        )
    )
    report: MaintenanceReport = assemble_deterministic_report(
        prepared,
        ("The analysis reported a visual anomaly.",),
        report_id=report_id,
        generated_at=generated_at,
    )
    return replace(result, maintenance_report=report)
