import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from modules.retriever.exceptions import RetrievalUnavailableError
from modules.retriever.models import EmbeddingIdentity

EmbeddingVector = tuple[float, ...]


class TextEmbedder(Protocol):
    @property
    def identity(self) -> EmbeddingIdentity: ...

    def embed_documents(self, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]: ...

    def embed_query(self, text: str) -> EmbeddingVector: ...


class SentenceTransformerEmbedder:
    """Offline-only SentenceTransformer adapter with explicit immutable embeddings."""

    def __init__(
        self,
        model_path: Path,
        identity: EmbeddingIdentity,
        *,
        device: str = "cpu",
    ) -> None:
        if not model_path.is_dir():
            raise RetrievalUnavailableError(
                "Prepared retrieval embedding model is not available; run "
                "scripts/download_retriever_encoder.py"
            )
        identity_path = model_path / "retriever_encoder_identity.json"
        try:
            prepared_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RetrievalUnavailableError(
                "Prepared retrieval embedding identity is not available or invalid"
            ) from exc
        expected_identity = {
            "model_id": identity.model_id,
            "revision": identity.revision,
            "embedding_dimension": identity.dimension,
        }
        if any(prepared_identity.get(key) != value for key, value in expected_identity.items()):
            raise RetrievalUnavailableError(
                "Prepared retrieval embedding identity does not match configuration"
            )
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(
                str(model_path),
                device=device,
                local_files_only=True,
            )
        except Exception as exc:
            raise RetrievalUnavailableError(
                "Prepared retrieval embedding model could not be loaded locally"
            ) from exc
        actual_dimension = model.get_embedding_dimension()
        if actual_dimension != identity.dimension:
            raise RetrievalUnavailableError(
                "Prepared retrieval embedding dimension does not match configured identity"
            )
        self._model = model
        self._identity = identity

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    def embed_documents(self, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]:
        if not texts:
            return ()
        vectors = self._model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return _freeze_vectors(vectors.tolist(), self._identity.dimension)

    def embed_query(self, text: str) -> EmbeddingVector:
        if not text.strip():
            raise ValueError("Retrieval query text cannot be empty")
        return self.embed_documents((text,))[0]


def validate_vector(vector: Sequence[float], expected_dimension: int) -> EmbeddingVector:
    if len(vector) != expected_dimension:
        raise ValueError(
            f"Embedding dimension must be {expected_dimension}; received {len(vector)}"
        )
    frozen = tuple(float(value) for value in vector)
    if not all(math.isfinite(value) for value in frozen):
        raise ValueError("Embedding vectors must contain only finite values")
    return frozen


def _freeze_vectors(
    vectors: Sequence[Sequence[float]],
    expected_dimension: int,
) -> tuple[EmbeddingVector, ...]:
    return tuple(validate_vector(vector, expected_dimension) for vector in vectors)
