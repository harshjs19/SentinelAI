from pathlib import Path

import numpy as np
import pytest

from modules.vision.encoder import FrozenResNet18Encoder
from modules.vision.input import VisionInput

_ENCODER_PATH = Path("models/pretrained/resnet18")
_IDENTITY_PATH = _ENCODER_PATH / "sentinelai_encoder.json"


@pytest.mark.skipif(not _IDENTITY_PATH.is_file(), reason="local ResNet-18 assets are optional")
def test_prepared_resnet18_cpu_smoke_is_frozen_finite_and_deterministic() -> None:
    encoder = FrozenResNet18Encoder(_ENCODER_PATH, "cpu")
    image = VisionInput(np.zeros((32, 48, 3), dtype=np.uint8))

    first = encoder.encode_batch((image,))
    second = encoder.encode_batch((image,))

    assert encoder.device == "cpu"
    assert not encoder.parameters_require_grad
    assert first.global_embeddings.shape == (1, 512)
    assert first.patch_embeddings.shape == (1, 16, 16, 384)
    assert np.isfinite(first.global_embeddings).all()
    assert np.array_equal(first.global_embeddings, second.global_embeddings)
    assert np.array_equal(first.patch_embeddings, second.patch_embeddings)
