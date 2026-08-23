from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class AudioInput:
    waveform: NDArray[np.float32]
    sample_rate: int

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("Audio sample rate must be positive")
        if self.waveform.ndim != 1 or self.waveform.size == 0:
            raise ValueError("Audio waveform must be non-empty mono audio")
        if not np.isfinite(self.waveform).all():
            raise ValueError("Audio waveform must contain only finite samples")
