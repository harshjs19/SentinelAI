from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
from sklearn.pipeline import Pipeline

from modules.thermal.config import (
    CONDITION_LABELS,
    DATASET_DOI,
    DATASET_LICENSE,
    DATASET_VERSION,
    SPEED_RPM,
    SUPPORTED_ASSET_TYPES,
    TEST_SPEEDS,
    TRAIN_SPEEDS,
    VALIDATION_SPEEDS,
)
from modules.vision.encoder import VisionEncoderMetadata

THERMAL_ARTIFACT_FORMAT_VERSION = 1
THERMAL_DATASET_NAME = "Rotating electromechanical system dataset for condition monitoring"
THERMAL_KNOWN_LIMITATIONS = (
    "Temporally correlated frames are not independent experiments",
    "Speed holdout uses the same test bench and fault installation",
    "No unseen-machine, unseen-camera, or production-plant generalization is established",
    "Component disassembly and reassembly can confound condition appearance",
    "Thermographic RGB is not a calibrated temperature matrix",
    "Raw confidence is not severity, failure probability, health, or risk",
    "No confidence calibration or multimodal fusion",
)


@dataclass(frozen=True)
class ThermalArtifactMetadata:
    format_version: int
    dataset_doi: str
    dataset_version: str
    dataset_license: str
    dataset_files: tuple[dict[str, object], ...]
    data_representation: str
    condition_mapping: dict[str, str]
    speed_rpm_mapping: dict[str, int]
    split: dict[str, object]
    supported_asset_types: tuple[str, ...]
    preprocessing: dict[str, object]
    encoder: VisionEncoderMetadata
    embedding_dimension: int
    candidate_parameters: dict[str, dict[str, object]]
    validation_metrics: dict[str, dict[str, object]]
    selection_metric: str
    selected_model: str
    final_fit_speeds: tuple[str, ...]
    locked_test_speed: str
    final_test_metrics: dict[str, object]
    experiment_test_metrics: dict[str, object]
    training_counts: dict[str, object]
    confidence_semantics: str
    dataset_name: str = THERMAL_DATASET_NAME
    class_names: tuple[str, ...] = tuple(CONDITION_LABELS.values())
    known_limitations: tuple[str, ...] = THERMAL_KNOWN_LIMITATIONS

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ThermalModelArtifact:
    pipeline: Pipeline
    metadata: ThermalArtifactMetadata


def save_thermal_artifact(artifact: ThermalModelArtifact, path: Path) -> None:
    validate_thermal_artifact(artifact)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)


def load_thermal_artifact(path: Path) -> ThermalModelArtifact:
    try:
        artifact = joblib.load(path)
    except FileNotFoundError:
        raise
    except Exception as error:
        raise ValueError("Thermal model artifact could not be loaded") from error
    if not isinstance(artifact, ThermalModelArtifact):
        raise ValueError("Thermal model artifact has an invalid payload")
    validate_thermal_artifact(artifact)
    return artifact


def validate_thermal_artifact(artifact: ThermalModelArtifact) -> None:
    metadata = artifact.metadata
    if metadata.format_version != THERMAL_ARTIFACT_FORMAT_VERSION:
        raise ValueError("Unsupported Thermal artifact format version")
    if metadata.condition_mapping != CONDITION_LABELS:
        raise ValueError("Thermal artifact condition labels are incompatible")
    if metadata.dataset_name != THERMAL_DATASET_NAME:
        raise ValueError("Thermal artifact dataset name is incompatible")
    if metadata.class_names != tuple(CONDITION_LABELS.values()):
        raise ValueError("Thermal artifact class order is incompatible")
    if metadata.known_limitations != THERMAL_KNOWN_LIMITATIONS:
        raise ValueError("Thermal artifact limitations are incompatible")
    if (
        metadata.dataset_doi != DATASET_DOI
        or metadata.dataset_version != DATASET_VERSION
        or metadata.dataset_license != DATASET_LICENSE
    ):
        raise ValueError("Thermal artifact dataset identity is incompatible")
    if metadata.speed_rpm_mapping != SPEED_RPM:
        raise ValueError("Thermal artifact speed metadata is incompatible")
    if metadata.supported_asset_types != SUPPORTED_ASSET_TYPES:
        raise ValueError("Thermal artifact asset types are incompatible")
    if metadata.embedding_dimension != 512 or metadata.encoder.global_dimension != 512:
        raise ValueError("Thermal artifact must use 512-dimensional global embeddings")
    if metadata.encoder.classification_logits_used:
        raise ValueError("Thermal artifact must not use ImageNet classification logits")
    if metadata.preprocessing != metadata.encoder.preprocessing:
        raise ValueError("Thermal artifact preprocessing does not match its encoder")
    if metadata.final_fit_speeds != TRAIN_SPEEDS + VALIDATION_SPEEDS:
        raise ValueError("Thermal artifact final-fit split is incompatible")
    if metadata.locked_test_speed != TEST_SPEEDS[0]:
        raise ValueError("Thermal artifact locked test split is incompatible")
    if not hasattr(artifact.pipeline, "predict_proba") or not hasattr(
        artifact.pipeline, "classes_"
    ):
        raise ValueError("Thermal artifact classifier must support class probabilities")
    expected_labels = set(CONDITION_LABELS.values())
    if {str(label) for label in artifact.pipeline.classes_} != expected_labels:
        raise ValueError("Thermal artifact classifier labels are incompatible")
