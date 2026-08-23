from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from modules.audio.embedding_cache import (
    CACHE_FORMAT_VERSION,
    EmbeddingCacheMetadata,
    StaleEmbeddingCacheError,
    load_embedding_cache,
    save_embedding_cache,
)
from modules.audio.encoder import AudioEncoderMetadata, validate_embedding_matrix
from modules.audio.input import AudioInput


class FakeAudioEncoder:
    def __init__(self, metadata: AudioEncoderMetadata) -> None:
        self._metadata = metadata

    @property
    def metadata(self) -> AudioEncoderMetadata:
        return self._metadata

    @property
    def device(self) -> str:
        return "fake-cpu"

    def encode_batch(self, inputs: tuple[AudioInput, ...]) -> np.ndarray:
        return np.asarray(
            [[float(np.mean(audio.waveform)), float(np.std(audio.waveform))] for audio in inputs],
            dtype=np.float64,
        )


def encoder_metadata() -> AudioEncoderMetadata:
    return AudioEncoderMetadata(
        model_id="fake/ast",
        revision="revision-a",
        license="test",
        representation="pooled-hidden",
        dimension=2,
        preprocessing_identity="fake-v1",
        preprocessing_config={"sampling_rate": 16_000},
    )


def test_fake_encoder_is_deterministic_and_has_expected_shape() -> None:
    encoder = FakeAudioEncoder(encoder_metadata())
    audio = AudioInput(np.asarray([0.0, 1.0, -1.0], dtype=np.float32), 16_000)

    first = encoder.encode_batch((audio,))
    second = encoder.encode_batch((audio,))

    validate_embedding_matrix(first, expected_rows=1, expected_dimension=2)
    assert np.array_equal(first, second)


def test_embedding_validation_rejects_shape_and_non_finite_values() -> None:
    with pytest.raises(ValueError, match="shape"):
        validate_embedding_matrix(np.zeros((1, 3)), expected_rows=1, expected_dimension=2)
    with pytest.raises(ValueError, match="non-finite"):
        validate_embedding_matrix(
            np.asarray([[0.0, np.nan]]),
            expected_rows=1,
            expected_dimension=2,
        )


def test_embedding_cache_round_trip_and_revision_invalidation(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.npz"
    paths = ("train/a.wav", "test/b.wav")
    embeddings = np.asarray([[1.0, 2.0], [3.0, 4.0]])
    metadata = EmbeddingCacheMetadata(
        CACHE_FORMAT_VERSION,
        "md5:dataset",
        encoder_metadata(),
    )
    save_embedding_cache(path, paths, embeddings, metadata)

    loaded = load_embedding_cache(path, paths, metadata)

    assert np.array_equal(loaded, embeddings)
    stale = replace(metadata, encoder=replace(metadata.encoder, revision="revision-b"))
    with pytest.raises(StaleEmbeddingCacheError, match="metadata"):
        load_embedding_cache(path, paths, stale)


def test_embedding_cache_representation_change_is_stale(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.npz"
    paths = ("train/a.wav",)
    embeddings = np.asarray([[1.0, 2.0]])
    metadata = EmbeddingCacheMetadata(
        CACHE_FORMAT_VERSION,
        "md5:dataset",
        encoder_metadata(),
    )
    save_embedding_cache(path, paths, embeddings, metadata)

    changed = replace(
        metadata,
        encoder=replace(metadata.encoder, representation="different-pooling"),
    )

    with pytest.raises(StaleEmbeddingCacheError, match="metadata"):
        load_embedding_cache(path, paths, changed)
