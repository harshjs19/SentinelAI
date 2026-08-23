from dataclasses import dataclass
from pathlib import Path

DATASET_SOURCE = "https://zenodo.org/records/6529888"
DATASET_DOI = "10.5281/zenodo.6529888"
DATASET_LICENSE = "CC BY 4.0"
DATASET_ARCHIVE = "bearing.zip"
DATASET_CHECKSUM = "md5:6381a00f9efc0ced779c8ad847e4ff59"
SUPPORTED_ASSET_TYPES = ("bearing",)

AST_MODEL_ID = "MIT/ast-finetuned-audioset-10-10-0.4593"
AST_MODEL_REVISION = "f826b80d28226b62986cc218e5cec390b1096902"
AST_MODEL_LICENSE = "BSD-3-Clause"
AST_REPRESENTATION = "mean_cls_distillation_tokens_last_hidden_state"
AST_EMBEDDING_DIMENSION = 768
AST_PREPROCESSING_IDENTITY = "transformers.ASTFeatureExtractor:preprocessor_config.json:v1"


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


@dataclass(frozen=True)
class AudioV2TrainingConfig:
    dataset_root: Path = Path("datasets/mimii_dg/bearing")
    encoder_path: Path = Path("models/pretrained/ast-audioset")
    embedding_cache_path: Path = Path("datasets/derived/mimii_dg_bearing_ast/embeddings.npz")
    artifact_path: Path = Path("models/audio_ast_bearing_anomaly_detector.joblib")
    runtime_artifact_path: Path = Path("models/audio_bearing_anomaly_detector.joblib")
    evaluation_path: Path = Path("evaluation/audio_v2_results.json")
    device: str = "cpu"
    embedding_batch_size: int = 4
    random_seed: int = 42
    calibration_stride: int = 5
    threshold_percentile: float = 0.99
    knn_neighbors: int = 5
    mahalanobis_pca_components: int = 128
