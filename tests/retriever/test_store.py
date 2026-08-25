from pathlib import Path

import pytest

from modules.retriever.config import COLLECTION_NAME, MANIFEST_PATH, REPOSITORY_ROOT
from modules.retriever.corpus import load_corpus
from modules.retriever.exceptions import StaleKnowledgeIndexError
from modules.retriever.models import EmbeddingIdentity
from modules.retriever.store import ChromaKnowledgeStore
from tests.retriever.support import FAKE_IDENTITY, FakeEmbedder


def test_collection_creation_cosine_query_filter_and_idempotent_upsert(
    tmp_path: Path,
) -> None:
    corpus = load_corpus(MANIFEST_PATH, FAKE_IDENTITY, repository_root=REPOSITORY_ROOT)
    embedder = FakeEmbedder()
    embeddings = embedder.embed_documents([chunk.text for chunk in corpus.chunks])
    store = ChromaKnowledgeStore(tmp_path / "chroma", COLLECTION_NAME)

    first = store.build(corpus, embeddings)
    second = store.build(corpus, embeddings)
    matches = store.query_tiered(
        embedder.embed_query("bearing fault bearing condition inspection"),
        fault_code="bearing_fault",
        asset_type="bearing",
        n_results=3,
        embedding_dimension=FAKE_IDENTITY.dimension,
    )

    assert first.rebuilt is True
    assert second.rebuilt is False
    assert first.chunk_count == second.chunk_count == len(corpus.chunks)
    assert store.metadata()["distance_metric"] == "cosine"
    assert matches
    assert all(match.chunk.fault_code == "bearing_fault" for match in matches)
    assert all(match.chunk.asset_type == "bearing" for match in matches)
    assert all(-1 <= match.similarity <= 1 for match in matches)


def test_generic_fallback_and_unrelated_fault_filtering(tmp_path: Path) -> None:
    corpus, embedder, store = _built_store(tmp_path)

    matches = store.query_tiered(
        embedder.embed_query("visual anomaly inspection unidentified physical fault"),
        fault_code="visual_anomaly",
        asset_type="pcb1",
        n_results=3,
        embedding_dimension=corpus.embedding_identity.dimension,
    )

    assert matches
    assert all(match.chunk.asset_type == "generic" for match in matches)
    assert all(match.chunk.fault_code == "visual_anomaly" for match in matches)
    assert all("bearing" not in match.chunk.source_id for match in matches)


def test_corpus_or_embedding_change_rebuilds_and_old_identity_becomes_stale(
    tmp_path: Path,
) -> None:
    corpus, _embedder, store = _built_store(tmp_path)
    changed_identity = EmbeddingIdentity("fake/changed", "second", 8)
    changed_embedder = FakeEmbedder(changed_identity)
    changed_corpus = load_corpus(
        MANIFEST_PATH,
        changed_identity,
        repository_root=REPOSITORY_ROOT,
    )

    result = store.build(
        changed_corpus,
        changed_embedder.embed_documents([chunk.text for chunk in changed_corpus.chunks]),
    )

    assert result.rebuilt is True
    with pytest.raises(StaleKnowledgeIndexError, match="stale"):
        store.validate_identity(
            corpus_digest_sha256=corpus.corpus_digest_sha256,
            embedding_identity=corpus.embedding_identity,
        )
    store.validate_identity(
        corpus_digest_sha256=changed_corpus.corpus_digest_sha256,
        embedding_identity=changed_identity,
    )


def test_embedding_dimension_is_rejected_before_chroma(tmp_path: Path) -> None:
    corpus = load_corpus(MANIFEST_PATH, FAKE_IDENTITY, repository_root=REPOSITORY_ROOT)
    store = ChromaKnowledgeStore(tmp_path / "chroma", COLLECTION_NAME)

    with pytest.raises(ValueError, match="dimension"):
        store.build(corpus, [[0.0]] * len(corpus.chunks))


def _built_store(
    tmp_path: Path,
) -> tuple[object, FakeEmbedder, ChromaKnowledgeStore]:
    corpus = load_corpus(MANIFEST_PATH, FAKE_IDENTITY, repository_root=REPOSITORY_ROOT)
    embedder = FakeEmbedder()
    store = ChromaKnowledgeStore(tmp_path / "chroma", COLLECTION_NAME)
    store.build(corpus, embedder.embed_documents([chunk.text for chunk in corpus.chunks]))
    return corpus, embedder, store
