from dataclasses import dataclass
from pathlib import Path

DATASET_SOURCE = "https://github.com/UTK-ASL/Dataset_digital_twin_predictive_maintenance"
DATASET_REVISION = "6376d4acaccc95472e22e5c44ce9ee2d35b28c89"

RAW_FEATURES = (
    "ch1_bias",
    "ch1_derivedPk",
    "ch1_direct",
    "ch1_directRMS",
    "ch1_velocityPk",
    "ch1_velocityRMS",
)
FEATURE_NAMES = tuple(
    f"{feature}_{statistic}" for feature in RAW_FEATURES for statistic in ("mean", "std")
)


@dataclass(frozen=True)
class TimeseriesTrainingConfig:
    dataset_root: Path = Path(
        "datasets/utk_digital_twin_predictive_maintenance/data/BentlyNevada_System1"
    )
    artifact_path: Path = Path("models/timeseries_fault_classifier.joblib")
    evaluation_path: Path = Path("evaluation/timeseries_baseline_results.json")
    random_seed: int = 42
    train_fraction: float = 0.6
    validation_fraction: float = 0.2
    purge_windows: int = 5
    random_forest_estimators: int = 300
