import io

import numpy as np
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError

from modules.thermal.input import ThermalInput
from modules.vision.config import VisionPreprocessingConfig
from modules.vision.input import VisionInput
from modules.vision.preprocessing import ResizeGeometry, preprocess_image

_SUPPORTED_FORMATS = {"JPEG", "PNG"}
_SUPPORTED_MODES = {"1", "L", "LA", "P", "RGB", "RGBA", "CMYK"}


def decode_thermal_image(content: bytes) -> ThermalInput:
    if not content:
        raise ValueError("Thermal input is not a valid JPEG or PNG image")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in _SUPPORTED_FORMATS or image.mode not in _SUPPORTED_MODES:
                raise ValueError("Thermal input must be a supported JPEG or PNG image")
            image.load()
            if image.width <= 0 or image.height <= 0:
                raise ValueError("Thermal input must have positive dimensions")
            pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
        raise ValueError("Thermal input is not a valid JPEG or PNG image") from error
    return ThermalInput(np.ascontiguousarray(pixels))


def preprocess_thermal_image(
    image: ThermalInput,
    config: VisionPreprocessingConfig,
) -> tuple[NDArray[np.float32], ResizeGeometry]:
    return preprocess_image(VisionInput(image.pixels), config)
