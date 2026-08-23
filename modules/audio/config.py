from dataclasses import dataclass
from pathlib import Path

DATASET_SOURCE = "https://zenodo.org/records/6529888"
DATASET_DOI = "10.5281/zenodo.6529888"
DATASET_LICENSE = "CC BY 4.0"
DATASET_ARCHIVE = "bearing.zip"
DATASET_CHECKSUM = "md5:6381a00f9efc0ced779c8ad847e4ff59"
SUPPORTED_ASSET_TYPES = ("bearing",)


@dataclass(frozen=True)
class AudioFeatureConfig:
    sample_rate: int = 16_000
    n_mels: int = 64
    n_fft: int = 1_024
    hop_length: int = 512
    fmin: float = 20.0
    fmax: float = 8_000.0


@dataclass(frozen=True)
class AudioTrainingConfig:
    dataset_root: Path = Path("datasets/mimii_dg/bearing")
    artifact_path: Path = Path("models/audio_bearing_anomaly_detector.joblib")
    evaluation_path: Path = Path("evaluation/audio_baseline_results.json")
    random_seed: int = 42
    calibration_stride: int = 5
    threshold_percentile: float = 0.99
    pca_variance_retained: float = 0.95
    isolation_forest_estimators: int = 300
    feature: AudioFeatureConfig = AudioFeatureConfig()
