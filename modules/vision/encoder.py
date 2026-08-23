import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from modules.vision.config import VisionPreprocessingConfig
from modules.vision.input import VisionInput
from modules.vision.preprocessing import preprocess_image

ENCODER_IDENTITY_FILENAME = "sentinelai_encoder.json"


@dataclass(frozen=True)
class VisionEncoderMetadata:
    model_id: str
    weights_id: str
    weights_filename: str
    weights_sha256: str
    weights_bytes: int
    torchvision_version: str
    global_layer: str
    global_dimension: int
    patch_layers: tuple[str, ...]
    patch_dimension: int
    patch_grid: tuple[int, int]
    preprocessing: dict[str, object]
    classification_logits_used: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class VisionFeatures:
    global_embeddings: NDArray[np.float64]
    patch_embeddings: NDArray[np.float64]


class VisionFeatureEncoder(Protocol):
    @property
    def metadata(self) -> VisionEncoderMetadata: ...

    @property
    def device(self) -> str: ...

    def encode_batch(self, inputs: Sequence[VisionInput]) -> VisionFeatures: ...


class FrozenResNet18Encoder:
    def __init__(
        self,
        model_path: Path,
        device: str = "cpu",
        expected_metadata: VisionEncoderMetadata | None = None,
    ) -> None:
        try:
            import torch
            import torchvision
            from torchvision.models import resnet18
        except ImportError as error:  # pragma: no cover - dependency integrity failure
            raise RuntimeError("Vision runtime dependencies are not installed") from error

        identity = load_encoder_identity(model_path)
        _verify_prepared_weight(model_path, identity)
        self._metadata = _metadata_from_identity(identity)
        if expected_metadata is not None:
            validate_encoder_metadata(self._metadata, expected_metadata)
        if self._metadata.torchvision_version != torchvision.__version__:
            raise ValueError("Local ResNet torchvision version does not match its identity")

        self._torch = torch
        self._device = _resolve_device(device, torch)
        self._model = resnet18(weights=None)
        state_dict = torch.load(
            model_path / self._metadata.weights_filename,
            map_location="cpu",
            weights_only=True,
        )
        self._model.load_state_dict(state_dict, strict=True)
        self._model.requires_grad_(False)
        self._model.eval()
        self._model.to(self._device)
        preprocessing = self._metadata.preprocessing
        self._preprocessing = VisionPreprocessingConfig(
            canvas_size=int(preprocessing["canvas_size"]),
            imagenet_mean=tuple(preprocessing["imagenet_mean"]),  # type: ignore[arg-type]
            imagenet_std=tuple(preprocessing["imagenet_std"]),  # type: ignore[arg-type]
            resize_interpolation=str(preprocessing["resize_interpolation"]),
            mask_interpolation=str(preprocessing["mask_interpolation"]),
            padding=str(preprocessing["padding"]),
        )

    @property
    def metadata(self) -> VisionEncoderMetadata:
        return self._metadata

    @property
    def device(self) -> str:
        return str(self._device)

    @property
    def parameters_require_grad(self) -> bool:
        return any(parameter.requires_grad for parameter in self._model.parameters())

    def encode_batch(self, inputs: Sequence[VisionInput]) -> VisionFeatures:
        if not inputs:
            raise ValueError("At least one Vision input is required")
        arrays = [preprocess_image(image, self._preprocessing)[0] for image in inputs]
        batch = self._torch.from_numpy(np.stack(arrays)).to(self._device)
        with self._torch.inference_mode():
            x = self._model.conv1(batch)
            x = self._model.bn1(x)
            x = self._model.relu(x)
            x = self._model.maxpool(x)
            x = self._model.layer1(x)
            layer2 = self._model.layer2(x)
            layer3 = self._model.layer3(layer2)
            layer4 = self._model.layer4(layer3)
            aligned_layer2 = self._torch.nn.functional.adaptive_avg_pool2d(
                layer2,
                layer3.shape[-2:],
            )
            patches = self._torch.cat((aligned_layer2, layer3), dim=1).permute(0, 2, 3, 1)
            global_embeddings = self._torch.nn.functional.adaptive_avg_pool2d(
                layer4,
                (1, 1),
            ).flatten(1)
        features = VisionFeatures(
            global_embeddings.detach().cpu().numpy().astype(np.float64, copy=False),
            patches.detach().cpu().numpy().astype(np.float64, copy=False),
        )
        validate_features(features, len(inputs), self._metadata)
        return features


def validate_features(
    features: VisionFeatures,
    expected_rows: int,
    metadata: VisionEncoderMetadata,
) -> None:
    expected_global = (expected_rows, metadata.global_dimension)
    expected_patches = (
        expected_rows,
        metadata.patch_grid[0],
        metadata.patch_grid[1],
        metadata.patch_dimension,
    )
    if features.global_embeddings.shape != expected_global:
        raise ValueError(
            "Vision encoder produced an invalid global embedding shape: "
            f"expected {expected_global}, got {features.global_embeddings.shape}"
        )
    if features.patch_embeddings.shape != expected_patches:
        raise ValueError(
            "Vision encoder produced an invalid patch embedding shape: "
            f"expected {expected_patches}, got {features.patch_embeddings.shape}"
        )
    if (
        not np.isfinite(features.global_embeddings).all()
        or not np.isfinite(features.patch_embeddings).all()
    ):
        raise ValueError("Vision encoder produced non-finite embeddings")


def load_encoder_identity(model_path: Path) -> dict[str, object]:
    identity_path = model_path / ENCODER_IDENTITY_FILENAME
    if not identity_path.is_file():
        raise FileNotFoundError("Prepared ResNet-18 encoder identity is missing")
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError("Prepared ResNet-18 encoder identity is invalid") from error
    if not isinstance(identity, dict):
        raise ValueError("Prepared ResNet-18 encoder identity is invalid")
    return identity


def validate_encoder_metadata(
    actual: VisionEncoderMetadata,
    expected: VisionEncoderMetadata,
) -> None:
    for name, actual_value, expected_value in (
        ("model identity", actual.model_id, expected.model_id),
        ("weights identity", actual.weights_id, expected.weights_id),
        ("weights checksum", actual.weights_sha256, expected.weights_sha256),
        ("torchvision version", actual.torchvision_version, expected.torchvision_version),
        ("global layer", actual.global_layer, expected.global_layer),
        ("global dimension", actual.global_dimension, expected.global_dimension),
        ("patch layers", actual.patch_layers, expected.patch_layers),
        ("patch dimension", actual.patch_dimension, expected.patch_dimension),
        ("patch grid", actual.patch_grid, expected.patch_grid),
        ("preprocessing", actual.preprocessing, expected.preprocessing),
    ):
        if actual_value != expected_value:
            raise ValueError(f"ResNet-18 encoder {name} does not match the Vision artifact")
    if actual.classification_logits_used or expected.classification_logits_used:
        raise ValueError("Vision artifact must not use ImageNet classification logits")


def preprocessing_metadata(config: VisionPreprocessingConfig) -> dict[str, object]:
    return {
        "canvas_size": config.canvas_size,
        "imagenet_mean": config.imagenet_mean,
        "imagenet_std": config.imagenet_std,
        "resize_interpolation": config.resize_interpolation,
        "mask_interpolation": config.mask_interpolation,
        "padding": config.padding,
    }


def _metadata_from_identity(identity: dict[str, object]) -> VisionEncoderMetadata:
    try:
        return VisionEncoderMetadata(
            model_id=str(identity["model_id"]),
            weights_id=str(identity["weights_id"]),
            weights_filename=str(identity["weights_filename"]),
            weights_sha256=str(identity["weights_sha256"]),
            weights_bytes=int(identity["weights_bytes"]),
            torchvision_version=str(identity["torchvision_version"]),
            global_layer=str(identity["global_layer"]),
            global_dimension=int(identity["global_dimension"]),
            patch_layers=tuple(identity["patch_layers"]),  # type: ignore[arg-type]
            patch_dimension=int(identity["patch_dimension"]),
            patch_grid=tuple(identity["patch_grid"]),  # type: ignore[arg-type]
            preprocessing=dict(identity["preprocessing"]),  # type: ignore[arg-type]
            classification_logits_used=bool(identity["classification_logits_used"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Prepared ResNet-18 encoder identity is incomplete") from error


def _verify_prepared_weight(model_path: Path, identity: dict[str, object]) -> None:
    try:
        weight_path = model_path / str(identity["weights_filename"])
        if weight_path.stat().st_size != int(identity["weights_bytes"]):
            raise ValueError("Prepared ResNet-18 weight size does not match its identity")
        digest = hashlib.sha256()
        with weight_path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != str(identity["weights_sha256"]):
            raise ValueError("Prepared ResNet-18 checksum does not match its identity")
    except FileNotFoundError as error:
        raise FileNotFoundError("Prepared ResNet-18 weights are missing") from error


def _resolve_device(requested: str, torch: object) -> object:
    normalized = requested.lower()
    if normalized == "auto":
        normalized = "cuda" if torch.cuda.is_available() else "cpu"  # type: ignore[attr-defined]
    if normalized not in {"cpu", "cuda"}:
        raise ValueError("Vision encoder device must be 'cpu', 'cuda', or 'auto'")
    if normalized == "cuda" and not torch.cuda.is_available():  # type: ignore[attr-defined]
        raise RuntimeError("CUDA was requested for Vision but is not available")
    return torch.device(normalized)  # type: ignore[attr-defined]
