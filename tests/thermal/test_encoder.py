from dataclasses import replace

import numpy as np
import pytest

from modules.thermal.encoder import validate_embeddings, validate_thermal_encoder_metadata
from modules.vision.encoder import VisionEncoderMetadata


def metadata() -> VisionEncoderMetadata:
    return VisionEncoderMetadata(
        model_id="resnet18",
        weights_id="imagenet-v1",
        weights_filename="weights.pth",
        weights_sha256="abc",
        weights_bytes=1,
        torchvision_version="test",
        global_layer="layer4_pool",
        global_dimension=512,
        patch_layers=("layer2", "layer3"),
        patch_dimension=384,
        patch_grid=(16, 16),
        preprocessing={"canvas_size": 256},
        classification_logits_used=False,
    )


def test_validates_finite_512_dimensional_embeddings() -> None:
    validate_embeddings(np.zeros((2, 512), dtype=np.float64), 2, 512)


@pytest.mark.parametrize(
    "embeddings",
    [
        np.zeros((2, 511), dtype=np.float64),
        np.full((2, 512), np.nan, dtype=np.float64),
    ],
)
def test_rejects_invalid_embeddings(embeddings: np.ndarray) -> None:
    with pytest.raises(ValueError, match="embedding|finite"):
        validate_embeddings(embeddings, 2, 512)


def test_rejects_logits_or_wrong_global_dimension() -> None:
    with pytest.raises(ValueError, match="global dimension"):
        validate_thermal_encoder_metadata(replace(metadata(), global_dimension=1000), metadata())
    with pytest.raises(ValueError, match="logits"):
        validate_thermal_encoder_metadata(
            replace(metadata(), classification_logits_used=True),
            replace(metadata(), classification_logits_used=True),
        )
