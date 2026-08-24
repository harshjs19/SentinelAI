from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from modules.thermal.input import ThermalInput
from modules.vision.encoder import (
    FrozenResNet18Encoder,
    VisionEncoderMetadata,
    validate_encoder_metadata,
)
from modules.vision.input import VisionInput


class ThermalFeatureEncoder(Protocol):
    @property
    def metadata(self) -> VisionEncoderMetadata: ...

    @property
    def device(self) -> str: ...

    def encode_batch(self, inputs: Sequence[ThermalInput]) -> NDArray[np.float64]: ...


class FrozenThermalResNet18Encoder:
    def __init__(
        self,
        model_path: Path,
        device: str = "cpu",
        expected_metadata: VisionEncoderMetadata | None = None,
    ) -> None:
        self._encoder = FrozenResNet18Encoder(model_path, device, expected_metadata)

    @property
    def metadata(self) -> VisionEncoderMetadata:
        return self._encoder.metadata

    @property
    def device(self) -> str:
        return self._encoder.device

    @property
    def parameters_require_grad(self) -> bool:
        return self._encoder.parameters_require_grad

    def encode_batch(self, inputs: Sequence[ThermalInput]) -> NDArray[np.float64]:
        if not inputs:
            raise ValueError("At least one Thermal input is required")
        vision_inputs = tuple(VisionInput(item.pixels) for item in inputs)
        embeddings = self._encoder.encode_batch(vision_inputs).global_embeddings
        validate_embeddings(embeddings, len(inputs), self.metadata.global_dimension)
        return embeddings


def validate_thermal_encoder_metadata(
    actual: VisionEncoderMetadata,
    expected: VisionEncoderMetadata,
) -> None:
    validate_encoder_metadata(actual, expected)
    if actual.global_dimension != 512:
        raise ValueError("Thermal encoder must produce 512-dimensional global embeddings")
    if actual.classification_logits_used:
        raise ValueError("Thermal encoder must not use ImageNet classification logits")


def validate_embeddings(
    embeddings: NDArray[np.float64],
    expected_rows: int,
    expected_dimension: int,
) -> None:
    expected = (expected_rows, expected_dimension)
    if embeddings.shape != expected:
        raise ValueError(
            "Thermal encoder produced an invalid embedding shape: "
            f"expected {expected}, got {embeddings.shape}"
        )
    if not np.isfinite(embeddings).all():
        raise ValueError("Thermal encoder produced non-finite embeddings")
