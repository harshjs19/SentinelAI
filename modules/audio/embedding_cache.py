import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from modules.audio.encoder import AudioEncoderMetadata, validate_embedding_matrix

CACHE_FORMAT_VERSION = 1


class StaleEmbeddingCacheError(ValueError):
    pass


@dataclass(frozen=True)
class EmbeddingCacheMetadata:
    format_version: int
    dataset_checksum: str
    encoder: AudioEncoderMetadata

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def save_embedding_cache(
    path: Path,
    relative_paths: tuple[str, ...],
    embeddings: NDArray[np.float64],
    metadata: EmbeddingCacheMetadata,
) -> None:
    validate_embedding_matrix(embeddings, len(relative_paths), metadata.encoder.dimension)
    if len(set(relative_paths)) != len(relative_paths):
        raise ValueError("Embedding cache paths must be unique")
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        relative_paths=np.asarray(relative_paths),
        embeddings=embeddings.astype(np.float32),
    )
    metadata_path(path).write_text(
        json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_embedding_cache(
    path: Path,
    expected_paths: tuple[str, ...],
    expected_metadata: EmbeddingCacheMetadata,
) -> NDArray[np.float64]:
    actual_metadata = _load_metadata(metadata_path(path))
    if actual_metadata != expected_metadata:
        raise StaleEmbeddingCacheError("Embedding cache metadata does not match")
    try:
        with np.load(path, allow_pickle=False) as cached:
            relative_paths = tuple(str(value) for value in cached["relative_paths"])
            embeddings = np.asarray(cached["embeddings"], dtype=np.float64)
    except (FileNotFoundError, KeyError, OSError, ValueError) as error:
        raise StaleEmbeddingCacheError("Embedding cache data is missing or invalid") from error
    if relative_paths != expected_paths:
        raise StaleEmbeddingCacheError("Embedding cache audio paths do not match")
    try:
        validate_embedding_matrix(
            embeddings,
            len(expected_paths),
            expected_metadata.encoder.dimension,
        )
    except ValueError as error:
        raise StaleEmbeddingCacheError(str(error)) from error
    return embeddings


def metadata_path(cache_path: Path) -> Path:
    return cache_path.with_suffix(".metadata.json")


def _load_metadata(path: Path) -> EmbeddingCacheMetadata:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        encoder = AudioEncoderMetadata(**raw["encoder"])
        return EmbeddingCacheMetadata(
            format_version=int(raw["format_version"]),
            dataset_checksum=str(raw["dataset_checksum"]),
            encoder=encoder,
        )
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise StaleEmbeddingCacheError("Embedding cache metadata is missing or invalid") from error
