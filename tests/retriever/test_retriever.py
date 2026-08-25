from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from domain.enums.modality import Modality
from modules.retriever.config import COLLECTION_NAME, MANIFEST_PATH, REPOSITORY_ROOT
from modules.retriever.corpus import KnowledgeCorpus, load_corpus
from modules.retriever.exceptions import InvalidEvidencePackageError
from modules.retriever.models import verify_retrieval_bundle_digest
from modules.retriever.retriever import KnowledgeRetriever
from modules.retriever.store import ChromaKnowledgeStore
from tests.retriever.support import FAKE_IDENTITY, FakeEmbedder, make_evidence_package


def test_retriever_rejects_tampered_evidence_package(tmp_path: Path) -> None:
    retriever, _corpus = _retriever(tmp_path)
    package = make_evidence_package("bearing_fault", asset_type="bearing")
    tampered = replace(package, machine=replace(package.machine, name="Tampered"))

    with pytest.raises(InvalidEvidencePackageError, match="verification failed"):
        retriever.retrieve(tampered)


def test_exact_fault_tier_citations_ordering_deduplication_and_bound(
    tmp_path: Path,
) -> None:
    retriever, corpus = _retriever(tmp_path, maximum_total_chunks=4)
    package = make_evidence_package("bearing_fault", asset_type="bearing")

    first = retriever.retrieve(package)
    second = retriever.retrieve(package)

    assert first == second
    assert first.evidence_package_id == package.package_id
    assert first.corpus_digest_sha256 == corpus.corpus_digest_sha256
    assert first.embedding_model_id == FAKE_IDENTITY.model_id
    assert len(first.chunks) <= 4
    assert len({chunk.chunk_id for chunk in first.chunks}) == len(first.chunks)
    assert first.chunks[0].fault_code == "bearing_fault"
    assert all(chunk.fault_code != "gear_wear_75" for chunk in first.chunks)
    assert all(
        chunk.title and chunk.publisher and chunk.source_uri and chunk.section
        for chunk in first.chunks
    )
    assert verify_retrieval_bundle_digest(first)


def test_generic_anomaly_fallback_never_infers_physical_fault(tmp_path: Path) -> None:
    retriever, _corpus = _retriever(tmp_path)

    bundle = retriever.retrieve(
        make_evidence_package("visual_anomaly", modality=Modality.VISION, asset_type="pcb1")
    )

    anomaly_chunks = [
        chunk for chunk in bundle.chunks if chunk.matched_intent == "maintenance:visual_anomaly"
    ]
    assert anomaly_chunks
    assert all(chunk.fault_code == "visual_anomaly" for chunk in anomaly_chunks)
    assert all(chunk.asset_type == "generic" for chunk in anomaly_chunks)
    assert all("bearing_damage_reference" not in chunk.source_id for chunk in bundle.chunks)


def test_insufficient_evidence_returns_no_fault_maintenance_result(tmp_path: Path) -> None:
    retriever, _corpus = _retriever(tmp_path)

    bundle = retriever.retrieve(make_evidence_package(None))

    assert {chunk.fault_code for chunk in bundle.chunks} <= {
        "insufficient_evidence",
        "evidence_limitations",
    }
    assert all(not chunk.matched_intent.startswith("maintenance:") for chunk in bundle.chunks)


def test_bundle_is_immutable_and_contains_no_raw_input_or_local_paths(tmp_path: Path) -> None:
    retriever, _corpus = _retriever(tmp_path)
    bundle = retriever.retrieve(make_evidence_package("acoustic_anomaly", modality=Modality.AUDIO))
    serialized_text = " ".join(chunk.text for chunk in bundle.chunks)

    with pytest.raises(FrozenInstanceError):
        bundle.collection_name = "changed"  # type: ignore[misc]
    assert "private fixture bytes" not in serialized_text
    assert "D:\\" not in serialized_text
    assert "knowledge/chroma" not in serialized_text
    assert not hasattr(bundle, "client")
    assert not hasattr(bundle, "model")


def _retriever(
    tmp_path: Path,
    *,
    maximum_total_chunks: int = 8,
) -> tuple[KnowledgeRetriever, KnowledgeCorpus]:
    corpus = load_corpus(MANIFEST_PATH, FAKE_IDENTITY, repository_root=REPOSITORY_ROOT)
    embedder = FakeEmbedder()
    store = ChromaKnowledgeStore(tmp_path / "chroma", COLLECTION_NAME)
    store.build(corpus, embedder.embed_documents([chunk.text for chunk in corpus.chunks]))
    return (
        KnowledgeRetriever(
            store=store,
            embedder=embedder,
            corpus_digest_sha256=corpus.corpus_digest_sha256,
            maximum_total_chunks=maximum_total_chunks,
        ),
        corpus,
    )
