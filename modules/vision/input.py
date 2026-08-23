from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class VisionInput:
    pixels: NDArray[np.uint8]

    def __post_init__(self) -> None:
        if self.pixels.ndim != 3 or self.pixels.shape[2] != 3:
            raise ValueError("Vision input must be an RGB image")
        if self.pixels.shape[0] <= 0 or self.pixels.shape[1] <= 0:
            raise ValueError("Vision input must have positive dimensions")
        if self.pixels.dtype != np.uint8:
            raise ValueError("Vision input pixels must use uint8 values")
