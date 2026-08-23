from dataclasses import dataclass
from pathlib import Path

VISA_SOURCE = "https://github.com/amazon-science/spot-diff"
VISA_ARCHIVE_URL = "https://amazon-visual-anomaly.s3.us-west-2.amazonaws.com/VisA_20220922.tar"
VISA_LICENSE = "CC BY 4.0"
VISA_SUBSET = "PCB1"
SUPPORTED_ASSET_TYPES = ("pcb1",)

RESNET_MODEL_ID = "torchvision.models.resnet18"
RESNET_WEIGHTS_ID = "ResNet18_Weights.IMAGENET1K_V1"
RESNET_WEIGHTS_URL = "https://download.pytorch.org/models/resnet18-f37072fd.pth"
RESNET_WEIGHTS_FILENAME = "resnet18-f37072fd.pth"
RESNET_WEIGHTS_BYTES = 46_830_571


@dataclass(frozen=True)
class VisionPreprocessingConfig:
    canvas_size: int = 256
    imagenet_mean: tuple[float, float, float] = (0.485, 0.456, 0.406)
    imagenet_std: tuple[float, float, float] = (0.229, 0.224, 0.225)
    resize_interpolation: str = "bilinear"
    mask_interpolation: str = "nearest"
    padding: str = "symmetric_imagenet_mean"


@dataclass(frozen=True)
class VisionTrainingConfig:
    dataset_root: Path = Path("datasets/visa")
    official_split_path: Path = Path("datasets/visa/split_csv/1cls.csv")
    encoder_path: Path = Path("models/pretrained/resnet18")
    feature_cache_path: Path = Path("datasets/derived/visa_pcb1_resnet18/features.npz")
    artifact_path: Path = Path("models/vision_pcb1_anomaly_detector.joblib")
    evaluation_path: Path = Path("evaluation/vision_baseline_results.json")
    device: str = "cpu"
    batch_size: int = 16
    random_seed: int = 42
    fit_fraction: float = 0.80
    patch_bank_max_size: int = 5_000
    image_score_percentile: float = 0.99
    image_threshold_percentile: float = 0.99
    pixel_threshold_percentile: float = 0.999
    preprocessing: VisionPreprocessingConfig = VisionPreprocessingConfig()
