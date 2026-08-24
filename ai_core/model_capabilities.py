from dataclasses import dataclass
from enum import StrEnum

from domain.enums.modality import Modality


class ModelLifecycleStatus(StrEnum):
    VALIDATED_BASELINE = "validated_baseline"
    EXPERIMENTAL = "experimental"
    REJECTED_EXPERIMENT = "rejected_experiment"


@dataclass(frozen=True)
class ModelCapability:
    model_id: str
    modality: Modality
    status: ModelLifecycleStatus
    runtime_default: bool
    validated_scope: str
    evaluation_reference: str


MODEL_CAPABILITIES: tuple[ModelCapability, ...] = (
    ModelCapability(
        model_id="timeseries_utk_v1",
        modality=Modality.TIMESERIES,
        status=ModelLifecycleStatus.VALIDATED_BASELINE,
        runtime_default=True,
        validated_scope="UTK blocked chronological within-recording multiclass evaluation",
        evaluation_reference="evaluation/timeseries_baseline_results.json",
    ),
    ModelCapability(
        model_id="audio_mimii_v1",
        modality=Modality.AUDIO,
        status=ModelLifecycleStatus.EXPERIMENTAL,
        runtime_default=True,
        validated_scope="MIMII DG bearing held-out Section 02 domain-shift evaluation",
        evaluation_reference="evaluation/audio_baseline_results.json",
    ),
    ModelCapability(
        model_id="audio_mimii_ast_v2",
        modality=Modality.AUDIO,
        status=ModelLifecycleStatus.REJECTED_EXPERIMENT,
        runtime_default=False,
        validated_scope="MIMII DG frozen-AST Section 01 promotion experiment",
        evaluation_reference="evaluation/audio_v2_results.json",
    ),
    ModelCapability(
        model_id="vision_visa_pcb1_v1",
        modality=Modality.VISION,
        status=ModelLifecycleStatus.EXPERIMENTAL,
        runtime_default=True,
        validated_scope="VisA PCB1 official one-class split evaluation",
        evaluation_reference="evaluation/vision_baseline_results.json",
    ),
    ModelCapability(
        model_id="thermal_cora_v1",
        modality=Modality.THERMAL,
        status=ModelLifecycleStatus.EXPERIMENTAL,
        runtime_default=True,
        validated_scope="CORA same-test-bench operating-speed-held-out evaluation",
        evaluation_reference="evaluation/thermal_baseline_results.json",
    ),
)
