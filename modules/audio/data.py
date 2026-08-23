import io
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from modules.audio.input import AudioInput

_CLIP_PATTERN = re.compile(
    r"^section_(?P<section>\d{2})_(?P<domain>source|target)_"
    r"(?P<split>train|test)_(?P<label>normal|anomaly)_\d{4}.*\.wav$"
)


@dataclass(frozen=True)
class AudioClip:
    path: Path
    section: str
    domain: str
    split: str
    label: str

    @property
    def is_anomaly(self) -> bool:
        return self.label == "anomaly"


def decode_wav(content: bytes) -> AudioInput:
    if not content:
        raise ValueError("Uploaded audio is empty")
    return _read_wav(io.BytesIO(content))


def load_wav(path: Path) -> AudioInput:
    return _read_wav(path)


def _read_wav(source: Path | io.BytesIO) -> AudioInput:
    try:
        with sf.SoundFile(source) as audio_file:
            if audio_file.format != "WAV":
                raise ValueError("Audio input must be a WAV file")
            sample_rate = audio_file.samplerate
            waveform = audio_file.read(dtype="float32", always_2d=True)
    except (sf.LibsndfileError, RuntimeError) as error:
        raise ValueError("Audio input is not a valid WAV file") from error

    mono = np.mean(waveform, axis=1, dtype=np.float32)
    return AudioInput(waveform=mono, sample_rate=sample_rate)


def discover_bearing_clips(dataset_root: Path) -> tuple[AudioClip, ...]:
    clips: list[AudioClip] = []
    for path in sorted(dataset_root.rglob("*.wav")):
        match = _CLIP_PATTERN.match(path.name)
        if match is None:
            raise ValueError(f"Unsupported MIMII DG bearing filename: {path.name}")
        clips.append(AudioClip(path=path, **match.groupdict()))
    if not clips:
        raise FileNotFoundError(f"No MIMII DG bearing WAV files found under: {dataset_root}")
    return tuple(clips)


def normal_training_clips(
    clips: Sequence[AudioClip],
    sections: set[str],
) -> tuple[AudioClip, ...]:
    return tuple(
        clip
        for clip in clips
        if clip.section in sections and clip.split == "train" and clip.label == "normal"
    )


def labeled_test_clips(clips: Sequence[AudioClip], section: str) -> tuple[AudioClip, ...]:
    return tuple(clip for clip in clips if clip.section == section and clip.split == "test")


def split_normal_calibration(
    clips: Sequence[AudioClip],
    stride: int,
) -> tuple[tuple[AudioClip, ...], tuple[AudioClip, ...]]:
    if stride < 2:
        raise ValueError("Calibration stride must be at least 2")

    groups: dict[tuple[str, str], list[AudioClip]] = defaultdict(list)
    for clip in clips:
        groups[(clip.section, clip.domain)].append(clip)

    fit: list[AudioClip] = []
    calibration: list[AudioClip] = []
    for key in sorted(groups):
        for index, clip in enumerate(sorted(groups[key], key=lambda item: item.path.name)):
            destination = calibration if index % stride == 0 else fit
            destination.append(clip)
    return tuple(fit), tuple(calibration)
