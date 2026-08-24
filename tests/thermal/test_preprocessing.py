import io

import numpy as np
import pytest
from PIL import Image

from modules.thermal.input import ThermalInput
from modules.thermal.preprocessing import decode_thermal_image, preprocess_thermal_image
from modules.vision.config import VisionPreprocessingConfig


def encoded_image(mode: str = "L", format_name: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (12, 6), color=100).save(buffer, format_name)
    return buffer.getvalue()


@pytest.mark.parametrize("format_name", ["PNG", "JPEG"])
def test_decodes_runtime_image_as_rgb(format_name: str) -> None:
    image = decode_thermal_image(encoded_image(format_name=format_name))

    assert image.pixels.shape == (6, 12, 3)
    assert image.pixels.dtype == np.uint8


def test_preprocessing_is_deterministic_and_preserves_aspect_with_padding() -> None:
    image = ThermalInput(np.full((6, 12, 3), 100, dtype=np.uint8))
    config = VisionPreprocessingConfig(canvas_size=16)

    first, geometry = preprocess_thermal_image(image, config)
    second, second_geometry = preprocess_thermal_image(image, config)

    assert first.shape == (3, 16, 16)
    assert np.isfinite(first).all()
    assert np.array_equal(first, second)
    assert geometry == second_geometry
    assert (geometry.resized_height, geometry.resized_width) == (8, 16)
    assert geometry.top == 4


@pytest.mark.parametrize("content", [b"", b"not-an-image"])
def test_rejects_malformed_runtime_image(content: bytes) -> None:
    with pytest.raises(ValueError, match="valid JPEG or PNG"):
        decode_thermal_image(content)


def test_rejects_malformed_in_memory_image() -> None:
    with pytest.raises(ValueError, match="RGB"):
        ThermalInput(np.zeros((4, 4), dtype=np.uint8))
