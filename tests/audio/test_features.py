import numpy as np
import pytest

from modules.audio.config import AudioFeatureConfig
from modules.audio.features import extract_audio_features, feature_names
from modules.audio.input import AudioInput


def sine_wave(sample_rate: int, duration: float = 1.0) -> np.ndarray:
    time = np.arange(int(sample_rate * duration), dtype=np.float32) / sample_rate
    return np.sin(2 * np.pi * 440 * time).astype(np.float32)


def test_extracts_deterministic_finite_features() -> None:
    config = AudioFeatureConfig(n_mels=16, n_fft=512, hop_length=256)
    audio = AudioInput(sine_wave(16_000), 16_000)

    first = extract_audio_features(audio, config)
    second = extract_audio_features(audio, config)

    assert first.shape == (32,)
    assert len(feature_names(config)) == 32
    assert np.isfinite(first).all()
    assert first == pytest.approx(second)


def test_resamples_non_target_sample_rate() -> None:
    config = AudioFeatureConfig(n_mels=16, n_fft=512, hop_length=256)
    audio = AudioInput(sine_wave(8_000), 8_000)

    features = extract_audio_features(audio, config)

    assert features.shape == (32,)
    assert np.isfinite(features).all()


def test_rejects_audio_too_short_for_fft() -> None:
    config = AudioFeatureConfig(n_mels=16, n_fft=512, hop_length=256)

    with pytest.raises(ValueError, match="too short"):
        extract_audio_features(AudioInput(np.ones(100, dtype=np.float32), 16_000), config)
