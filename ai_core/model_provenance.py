from dataclasses import dataclass

from ai_core.model_capabilities import (
    ModelCapability,
    ModelLifecycleStatus,
    validate_evaluation_reference,
    validate_model_id,
)
from domain.enums.modality import Modality


@dataclass(frozen=True)
class ProducingModelContext:
    model_id: str
    modality: Modality
    lifecycle_status: ModelLifecycleStatus
    runtime_default_at_execution: bool
    validated_scope: str
    evaluation_reference: str
    confidence_semantics: str

    def __post_init__(self) -> None:
        validate_model_id(self.model_id)
        if not self.validated_scope.strip():
            raise ValueError("Producing model context validated_scope cannot be empty")
        if not self.confidence_semantics.strip():
            raise ValueError("Producing model context confidence_semantics cannot be empty")
        validate_evaluation_reference(self.evaluation_reference)
        if (
            self.runtime_default_at_execution
            and self.lifecycle_status is ModelLifecycleStatus.REJECTED_EXPERIMENT
        ):
            raise ValueError("A rejected experiment cannot be a runtime-default producing model")


def snapshot_producing_model_context(
    capability: ModelCapability,
) -> ProducingModelContext:
    return ProducingModelContext(
        model_id=str(capability.model_id),
        modality=capability.modality,
        lifecycle_status=capability.status,
        runtime_default_at_execution=bool(capability.runtime_default),
        validated_scope=str(capability.validated_scope),
        evaluation_reference=str(capability.evaluation_reference),
        confidence_semantics=str(capability.confidence_semantics),
    )
