from pathlib import Path

import numpy as np
import pytest

from modules.thermal.encoder import FrozenThermalResNet18Encoder
from modules.thermal.input import ThermalInput

_ENCODER_PATH = Path("models/pretrained/resnet18")
_IDENTITY_PATH = _ENCODER_PATH / "sentinelai_encoder.json"


@pytest.mark.skipif(not _IDENTITY_PATH.is_file(), reason="local ResNet-18 assets are optional")
def test_prepared_thermal_resnet18_is_frozen_finite_and_deterministic() -> None:
    encoder = FrozenThermalResNet18Encoder(_ENCODER_PATH, "cpu")
    image = ThermalInput(np.zeros((32, 48, 3), dtype=np.uint8))

    first = encoder.encode_batch((image,))
    second = encoder.encode_batch((image,))

    assert encoder.device == "cpu"
    assert not encoder.parameters_require_grad
    assert first.shape == (1, 512)
    assert np.isfinite(first).all()
    assert np.array_equal(first, second)
