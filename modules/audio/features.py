from dataclasses import asdict

import librosa
import numpy as np
from numpy.typing import NDArray

from modules.audio.config import AudioFeatureConfig
from modules.audio.input import AudioInput


def feature_names(config: AudioFeatureConfig) -> tuple[str, ...]:
    return tuple(
        f"mel_{mel_band:02d}_{statistic}"
        for mel_band in range(config.n_mels)
        for statistic in ("mean", "std")
    )


def feature_config_metadata(config: AudioFeatureConfig) -> dict[str, object]:
    return {
        **asdict(config),
        "representation": "log_mel_db_summary",
        "statistics": ["mean", "std"],
        "power": 2.0,
        "center": False,
    }


def extract_audio_features(
    audio: AudioInput,
    config: AudioFeatureConfig,
) -> NDArray[np.float64]:
    waveform = audio.waveform
    if audio.sample_rate != config.sample_rate:
        waveform = librosa.resample(
            waveform,
            orig_sr=audio.sample_rate,
            target_sr=config.sample_rate,
        )
    if waveform.size < config.n_fft:
        raise ValueError("Audio waveform is too short for feature extraction")

    mel_power = librosa.feature.melspectrogram(
        y=waveform,
        sr=config.sample_rate,
        n_fft=config.n_fft,
        hop_length=config.hop_length,
        win_length=config.n_fft,
        window="hann",
        center=False,
        power=2.0,
        n_mels=config.n_mels,
        fmin=config.fmin,
        fmax=config.fmax,
    )
    log_mel = librosa.power_to_db(mel_power, ref=1.0, top_db=80.0)
    features = np.column_stack((log_mel.mean(axis=1), log_mel.std(axis=1))).reshape(-1)
    if features.size != len(feature_names(config)) or not np.isfinite(features).all():
        raise ValueError("Audio feature extraction produced invalid values")
    return features.astype(np.float64, copy=False)
