import math
from pathlib import Path

import pytest

from modules.retriever.embedding import SentenceTransformerEmbedder, validate_vector
from modules.retriever.exceptions import RetrievalUnavailableError
from tests.retriever.support import FAKE_IDENTITY, FakeEmbedder


def test_fake_embedder_has_deterministic_finite_immutable_document_and_query_vectors() -> None:
    embedder = FakeEmbedder()

    documents = embedder.embed_documents(["bearing inspection", "gear inspection"])
    query = embedder.embed_query("bearing inspection")

    assert documents[0] == query
    assert isinstance(documents, tuple)
    assert isinstance(documents[0], tuple)
    assert all(len(vector) == FAKE_IDENTITY.dimension for vector in documents)
    assert all(math.isfinite(value) for vector in documents for value in vector)


def test_incorrect_or_nonfinite_vector_is_rejected() -> None:
    with pytest.raises(ValueError, match="dimension"):
        validate_vector([0.1], 2)
    with pytest.raises(ValueError, match="finite"):
        validate_vector([0.1, float("nan")], 2)


def test_missing_sentence_transformer_assets_fail_without_download(tmp_path: Path) -> None:
    with pytest.raises(RetrievalUnavailableError, match="not available"):
        SentenceTransformerEmbedder(tmp_path / "missing", FAKE_IDENTITY)
