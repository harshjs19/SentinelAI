import io
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from modules.audio.data import (
    AudioClip,
    decode_wav,
    discover_bearing_clips,
    normal_training_clips,
    split_normal_calibration,
)


def wav_bytes(waveform: np.ndarray, sample_rate: int = 16_000) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, waveform, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def test_decodes_mono_wav() -> None:
    waveform = np.linspace(-0.5, 0.5, 1_600, dtype=np.float32)

    audio = decode_wav(wav_bytes(waveform))

    assert audio.sample_rate == 16_000
    assert audio.waveform.shape == (1_600,)
    assert np.isfinite(audio.waveform).all()


def test_downmixes_stereo_wav_to_mono() -> None:
    stereo = np.column_stack(
        (
            np.full(1_600, 0.5, dtype=np.float32),
            np.full(1_600, -0.5, dtype=np.float32),
        )
    )

    audio = decode_wav(wav_bytes(stereo))

    assert audio.waveform.shape == (1_600,)
    assert audio.waveform == pytest.approx(np.zeros(1_600), abs=1e-4)


@pytest.mark.parametrize("content", [b"", b"not-a-wav"])
def test_rejects_invalid_audio(content: bytes) -> None:
    with pytest.raises(ValueError, match="audio|WAV"):
        decode_wav(content)


def test_discovers_filename_metadata_without_using_it_as_features(tmp_path: Path) -> None:
    train = tmp_path / "train"
    test = tmp_path / "test"
    train.mkdir()
    test.mkdir()
    (train / "section_00_source_train_normal_0000_vel_6.wav").touch()
    (test / "section_01_target_test_anomaly_0000_vel_4_loc_A.wav").touch()

    clips = discover_bearing_clips(tmp_path)

    assert clips == (
        AudioClip(
            path=test / "section_01_target_test_anomaly_0000_vel_4_loc_A.wav",
            section="01",
            domain="target",
            split="test",
            label="anomaly",
        ),
        AudioClip(
            path=train / "section_00_source_train_normal_0000_vel_6.wav",
            section="00",
            domain="source",
            split="train",
            label="normal",
        ),
    )


def test_normal_training_and_calibration_exclude_anomalies(tmp_path: Path) -> None:
    clips = tuple(
        AudioClip(
            path=tmp_path / f"normal_{index}.wav",
            section="00",
            domain="source",
            split="train",
            label="normal",
        )
        for index in range(10)
    ) + (
        AudioClip(
            path=tmp_path / "anomaly.wav",
            section="00",
            domain="source",
            split="test",
            label="anomaly",
        ),
    )

    normal = normal_training_clips(clips, {"00"})
    fit, calibration = split_normal_calibration(normal, stride=5)

    assert len(normal) == 10
    assert len(fit) == 8
    assert len(calibration) == 2
    assert all(clip.label == "normal" and clip.split == "train" for clip in fit + calibration)
