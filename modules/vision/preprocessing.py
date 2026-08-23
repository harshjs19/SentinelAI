import io
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError

from modules.vision.config import VisionPreprocessingConfig
from modules.vision.input import VisionInput

_SUPPORTED_FORMATS = {"JPEG", "PNG"}
_SUPPORTED_MODES = {"1", "L", "LA", "P", "RGB", "RGBA", "CMYK"}


@dataclass(frozen=True)
class ResizeGeometry:
    original_height: int
    original_width: int
    resized_height: int
    resized_width: int
    top: int
    left: int
    canvas_size: int


def decode_image(content: bytes) -> VisionInput:
    if not content:
        raise ValueError("Vision input is not a valid JPEG or PNG image")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in _SUPPORTED_FORMATS or image.mode not in _SUPPORTED_MODES:
                raise ValueError("Vision input must be a supported JPEG or PNG image")
            image.load()
            if image.width <= 0 or image.height <= 0:
                raise ValueError("Vision input must have positive dimensions")
            pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
        raise ValueError("Vision input is not a valid JPEG or PNG image") from error
    return VisionInput(np.ascontiguousarray(pixels))


def preprocess_image(
    image: VisionInput,
    config: VisionPreprocessingConfig,
) -> tuple[NDArray[np.float32], ResizeGeometry]:
    geometry = resize_geometry(image.pixels.shape[:2], config.canvas_size)
    pil_image = Image.fromarray(image.pixels, mode="RGB")
    resized = pil_image.resize(
        (geometry.resized_width, geometry.resized_height),
        resample=Image.Resampling.BILINEAR,
    )
    mean = np.asarray(config.imagenet_mean, dtype=np.float32)
    canvas = np.broadcast_to(mean, (config.canvas_size, config.canvas_size, 3)).copy()
    resized_array = np.asarray(resized, dtype=np.float32) / 255.0
    canvas[
        geometry.top : geometry.top + geometry.resized_height,
        geometry.left : geometry.left + geometry.resized_width,
    ] = resized_array
    normalized = (canvas - mean) / np.asarray(config.imagenet_std, dtype=np.float32)
    tensor = np.transpose(normalized, (2, 0, 1)).astype(np.float32, copy=False)
    if not np.isfinite(tensor).all():
        raise ValueError("Vision preprocessing produced non-finite values")
    return tensor, geometry


def preprocess_mask(
    mask: NDArray[np.uint8],
    geometry: ResizeGeometry,
) -> NDArray[np.uint8]:
    if mask.ndim != 2 or mask.shape != (geometry.original_height, geometry.original_width):
        raise ValueError("Vision mask must align with its source image")
    binary = (mask > 0).astype(np.uint8)
    resized = Image.fromarray(binary, mode="L").resize(
        (geometry.resized_width, geometry.resized_height),
        resample=Image.Resampling.NEAREST,
    )
    canvas = np.zeros((geometry.canvas_size, geometry.canvas_size), dtype=np.uint8)
    canvas[
        geometry.top : geometry.top + geometry.resized_height,
        geometry.left : geometry.left + geometry.resized_width,
    ] = np.asarray(resized, dtype=np.uint8)
    if not set(np.unique(canvas)).issubset({0, 1}):  # pragma: no cover - invariant guard
        raise ValueError("Vision mask preprocessing must remain binary")
    return canvas


def resize_anomaly_map(
    anomaly_map: NDArray[np.float64],
    canvas_size: int,
) -> NDArray[np.float64]:
    if anomaly_map.ndim != 2 or not np.isfinite(anomaly_map).all():
        raise ValueError("Vision anomaly map must be a finite two-dimensional array")
    resized = Image.fromarray(anomaly_map.astype(np.float32), mode="F").resize(
        (canvas_size, canvas_size),
        resample=Image.Resampling.BILINEAR,
    )
    return np.asarray(resized, dtype=np.float64)


def resize_geometry(shape: tuple[int, int], canvas_size: int) -> ResizeGeometry:
    height, width = shape
    if height <= 0 or width <= 0 or canvas_size <= 0:
        raise ValueError("Vision resize dimensions must be positive")
    scale = min(canvas_size / width, canvas_size / height)
    resized_width = min(canvas_size, max(1, round(width * scale)))
    resized_height = min(canvas_size, max(1, round(height * scale)))
    return ResizeGeometry(
        original_height=height,
        original_width=width,
        resized_height=resized_height,
        resized_width=resized_width,
        top=(canvas_size - resized_height) // 2,
        left=(canvas_size - resized_width) // 2,
        canvas_size=canvas_size,
    )
