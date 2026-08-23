import io

import numpy as np
import pytest
from PIL import Image

from modules.vision.config import VisionPreprocessingConfig
from modules.vision.input import VisionInput
from modules.vision.preprocessing import decode_image, preprocess_image, preprocess_mask


def image_bytes(mode: str = "RGB", format_name: str = "PNG") -> bytes:
    if mode == "L":
        pixels = np.arange(24, dtype=np.uint8).reshape(4, 6)
    else:
        pixels = np.zeros((4, 6, 3), dtype=np.uint8)
        pixels[:, :3, 0] = 255
    buffer = io.BytesIO()
    Image.fromarray(pixels, mode=mode).save(buffer, format=format_name)
    return buffer.getvalue()


@pytest.mark.parametrize(("format_name", "magic"), [("PNG", b"\x89PNG"), ("JPEG", b"\xff\xd8")])
def test_decodes_image_bytes_by_content(format_name: str, magic: bytes) -> None:
    content = image_bytes(format_name=format_name)
    assert content.startswith(magic)

    image = decode_image(content)

    assert image.pixels.shape == (4, 6, 3)
    assert image.pixels.dtype == np.uint8


def test_converts_grayscale_to_rgb() -> None:
    image = decode_image(image_bytes(mode="L"))

    assert image.pixels.shape == (4, 6, 3)
    assert np.array_equal(image.pixels[..., 0], image.pixels[..., 1])


def test_rejects_malformed_image() -> None:
    with pytest.raises(ValueError, match="valid JPEG or PNG"):
        decode_image(b"not-an-image")


def test_preprocessing_is_deterministic_and_preserves_edges_with_padding() -> None:
    image = decode_image(image_bytes())
    config = VisionPreprocessingConfig(canvas_size=8)

    first, geometry = preprocess_image(image, config)
    second, repeated_geometry = preprocess_image(image, config)

    assert np.array_equal(first, second)
    assert geometry == repeated_geometry
    assert first.shape == (3, 8, 8)
    assert np.isfinite(first).all()
    assert geometry.resized_width == 8
    assert geometry.resized_height == 5
    assert geometry.top == 1


def test_mask_transform_is_aligned_and_remains_binary() -> None:
    pixels = np.zeros((4, 8, 3), dtype=np.uint8)
    pixels[:, 4:, 0] = 255
    mask = np.zeros((4, 8), dtype=np.uint8)
    mask[:, 4:] = 255
    config = VisionPreprocessingConfig(canvas_size=8)

    _, geometry = preprocess_image(VisionInput(pixels), config)
    transformed = preprocess_mask(mask, geometry)

    assert transformed.shape == (8, 8)
    assert set(np.unique(transformed)) == {0, 1}
    assert transformed[:, :4].sum() == 0
    assert transformed[:, 4:].sum() > 0
