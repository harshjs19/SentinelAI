import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath

from domain.enums.modality import Modality

_MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ModelLifecycleStatus(StrEnum):
    VALIDATED_BASELINE = "validated_baseline"
    EXPERIMENTAL = "experimental"
    REJECTED_EXPERIMENT = "rejected_experiment"


def validate_model_id(model_id: str) -> None:
    if _MODEL_ID_PATTERN.fullmatch(model_id) is None:
        raise ValueError("Model ID must be a concise path-free identifier")


def validate_evaluation_reference(reference: str) -> None:
    if not reference.strip():
        raise ValueError("Model capability evaluation_reference cannot be empty")
    posix_path = PurePosixPath(reference)
    windows_path = PureWindowsPath(reference)
    if (
        "\\" in reference
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in posix_path.parts
        or posix_path.parts[:1] != ("evaluation",)
        or posix_path.suffix != ".json"
    ):
        raise ValueError(
            "Model capability evaluation_reference must be a repository-relative "
            "evaluation/*.json path"
        )


@dataclass(frozen=True)
class ModelCapability:
    model_id: str
    modality: Modality
    status: ModelLifecycleStatus
    runtime_default: bool
    validated_scope: str
    evaluation_reference: str
    confidence_semantics: str

    def __post_init__(self) -> None:
        validate_model_id(self.model_id)
        if not self.validated_scope.strip():
            raise ValueError("Model capability validated_scope cannot be empty")
        if not self.confidence_semantics.strip():
            raise ValueError("Model capability confidence_semantics cannot be empty")
        validate_evaluation_reference(self.evaluation_reference)
        if self.runtime_default and self.status is ModelLifecycleStatus.REJECTED_EXPERIMENT:
            raise ValueError("A rejected experiment cannot be a runtime-default model")


MODEL_CAPABILITIES: tuple[ModelCapability, ...] = (
    ModelCapability(
        model_id="timeseries_utk_v1",
        modality=Modality.TIMESERIES,
        status=ModelLifecycleStatus.VALIDATED_BASELINE,
        runtime_default=True,
        validated_scope="UTK blocked chronological within-recording multiclass evaluation",
        evaluation_reference="evaluation/timeseries_baseline_results.json",
        confidence_semantics="raw_selected_class_predict_proba",
    ),
    ModelCapability(
        model_id="audio_mimii_v1",
        modality=Modality.AUDIO,
        status=ModelLifecycleStatus.EXPERIMENTAL,
        runtime_default=True,
        validated_scope="MIMII DG bearing held-out Section 02 domain-shift evaluation",
        evaluation_reference="evaluation/audio_baseline_results.json",
        confidence_semantics="bounded_empirical_anomaly_evidence_from_normal_calibration",
    ),
    ModelCapability(
        model_id="audio_mimii_ast_v2",
        modality=Modality.AUDIO,
        status=ModelLifecycleStatus.REJECTED_EXPERIMENT,
        runtime_default=False,
        validated_scope="MIMII DG frozen-AST Section 01 promotion experiment",
        evaluation_reference="evaluation/audio_v2_results.json",
        confidence_semantics="bounded_empirical_anomaly_evidence_from_normal_calibration",
    ),
    ModelCapability(
        model_id="vision_visa_pcb1_v1",
        modality=Modality.VISION,
        status=ModelLifecycleStatus.EXPERIMENTAL,
        runtime_default=True,
        validated_scope="VisA PCB1 official one-class split evaluation",
        evaluation_reference="evaluation/vision_baseline_results.json",
        confidence_semantics="bounded_empirical_visual_anomaly_evidence_from_normal_calibration",
    ),
    ModelCapability(
        model_id="thermal_cora_v1",
        modality=Modality.THERMAL,
        status=ModelLifecycleStatus.EXPERIMENTAL,
        runtime_default=True,
        validated_scope="CORA same-test-bench operating-speed-held-out evaluation",
        evaluation_reference="evaluation/thermal_baseline_results.json",
        confidence_semantics="raw_selected_class_predict_proba",
    ),
)


def validate_model_capabilities(capabilities: Sequence[ModelCapability]) -> None:
    model_ids = [capability.model_id for capability in capabilities]
    if len(set(model_ids)) != len(model_ids):
        raise ValueError("Model capability model IDs must be unique")

    for modality in Modality:
        get_runtime_default_capability(modality, capabilities)


def get_runtime_default_capability(
    modality: Modality,
    capabilities: Sequence[ModelCapability] = MODEL_CAPABILITIES,
) -> ModelCapability:
    matches = [
        capability
        for capability in capabilities
        if capability.modality is modality and capability.runtime_default
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one runtime-default capability for {modality.value}; "
            f"found {len(matches)}"
        )
    return matches[0]


validate_model_capabilities(MODEL_CAPABILITIES)
