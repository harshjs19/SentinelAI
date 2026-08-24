from dataclasses import dataclass
from pathlib import Path

from modules.vision.config import VisionPreprocessingConfig

DATASET_DOI = "doi:10.34810/DATA2500"
DATASET_VERSION = "2.1"
DATASET_LICENSE = "CC BY 4.0"
DATASET_SOURCE = "https://doi.org/10.34810/DATA2500"
RELATED_PAPER = "https://doi.org/10.1038/s41597-026-07224-0"
SUPPORTED_ASSET_TYPES = ("rotating_electromechanical_system",)

CONDITION_LABELS = {
    "H": "healthy",
    "BD": "bearing_fault",
    "HB": "half_broken_rotor_bar",
    "OB": "broken_rotor_bar",
    "U": "imbalance",
    "M": "misalignment",
    "W25": "gear_wear_25",
    "W50": "gear_wear_50",
    "W75": "gear_wear_75",
}
SPEED_RPM = {"F5": 300, "F15": 900, "F50": 3000, "F60": 3600}
TRAIN_SPEEDS = ("F5", "F15")
VALIDATION_SPEEDS = ("F50",)
TEST_SPEEDS = ("F60",)


@dataclass(frozen=True)
class ThermalTrainingConfig:
    dataset_root: Path = Path("datasets/thermal_condition_monitoring")
    encoder_path: Path = Path("models/pretrained/resnet18")
    embedding_cache_path: Path = Path("datasets/derived/thermal_resnet18/embeddings.npz")
    artifact_path: Path = Path("models/thermal_condition_classifier.joblib")
    evaluation_path: Path = Path("evaluation/thermal_baseline_results.json")
    device: str = "cpu"
    batch_size: int = 32
    random_seed: int = 42
    preprocessing: VisionPreprocessingConfig = VisionPreprocessingConfig()
