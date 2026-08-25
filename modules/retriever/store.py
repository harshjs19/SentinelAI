from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.retriever.config import DISTANCE_METRIC, KNOWLEDGE_SCHEMA_VERSION
from modules.retriever.corpus import KnowledgeCorpus
from modules.retriever.embedding import validate_vector
from modules.retriever.exceptions import RetrievalUnavailableError, StaleKnowledgeIndexError
from modules.retriever.models import EmbeddingIdentity, KnowledgeChunk, KnowledgeSourceKind


@dataclass(frozen=True)
class StoredSearchResult:
    chunk: KnowledgeChunk
    similarity: float


@dataclass(frozen=True)
class IndexBuildResult:
    rebuilt: bool
    chunk_count: int
    collection_metadata: tuple[tuple[str, str | int | float | bool], ...]


class ChromaKnowledgeStore:
    """Narrow local Chroma wrapper; callers always supply explicit embeddings."""

    def __init__(self, path: Path, collection_name: str) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=str(path))
        self._collection_name = collection_name

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def build(
        self,
        corpus: KnowledgeCorpus,
        embeddings: Sequence[Sequence[float]],
    ) -> IndexBuildResult:
        if len(embeddings) != len(corpus.chunks):
            raise ValueError("Each knowledge chunk must have exactly one embedding")
        frozen_embeddings = [
            list(validate_vector(vector, corpus.embedding_identity.dimension))
            for vector in embeddings
        ]
        expected_metadata = _collection_metadata(corpus)
        existing = self._collection_or_none()
        rebuilt = existing is None or not _metadata_matches(existing.metadata, expected_metadata)
        if rebuilt and existing is not None:
            self._client.delete_collection(self._collection_name)
            existing = None
        collection = existing or self._client.create_collection(
            name=self._collection_name,
            configuration={"hnsw": {"space": DISTANCE_METRIC}},
            metadata=expected_metadata,
            embedding_function=None,
        )
        if corpus.chunks:
            collection.upsert(
                ids=[chunk.chunk_id for chunk in corpus.chunks],
                embeddings=frozen_embeddings,
                documents=[chunk.text for chunk in corpus.chunks],
                metadatas=[_chunk_metadata(chunk) for chunk in corpus.chunks],
            )
        return IndexBuildResult(
            rebuilt=rebuilt,
            chunk_count=collection.count(),
            collection_metadata=tuple(sorted(expected_metadata.items())),
        )

    def validate_identity(
        self,
        *,
        corpus_digest_sha256: str,
        embedding_identity: EmbeddingIdentity,
    ) -> None:
        collection = self._collection_or_none()
        if collection is None:
            raise RetrievalUnavailableError(
                "Prepared knowledge index is not available; run the retriever build command"
            )
        expected = {
            "knowledge_schema_version": KNOWLEDGE_SCHEMA_VERSION,
            "corpus_digest_sha256": corpus_digest_sha256,
            "embedding_model_id": embedding_identity.model_id,
            "embedding_model_revision": embedding_identity.revision,
            "embedding_dimension": embedding_identity.dimension,
            "distance_metric": DISTANCE_METRIC,
        }
        if not _metadata_matches(collection.metadata, expected):
            raise StaleKnowledgeIndexError(
                "Prepared knowledge index is stale; rebuild it from the tracked corpus"
            )
        space = collection.configuration_json.get("hnsw", {}).get("space")
        if space != DISTANCE_METRIC:
            raise StaleKnowledgeIndexError("Prepared knowledge index distance metric is stale")

    def query_tiered(
        self,
        query_embedding: Sequence[float],
        *,
        fault_code: str,
        asset_type: str,
        n_results: int,
        embedding_dimension: int,
    ) -> tuple[StoredSearchResult, ...]:
        vector = validate_vector(query_embedding, embedding_dimension)
        collection = self._collection_or_none()
        if collection is None:
            raise RetrievalUnavailableError("Prepared knowledge index is not available")
        tiers = [asset_type]
        if asset_type != "generic":
            tiers.append("generic")
        results: list[StoredSearchResult] = []
        seen: set[str] = set()
        for tier_asset_type in tiers:
            remaining = n_results - len(results)
            if remaining <= 0:
                break
            raw = collection.query(
                query_embeddings=[list(vector)],
                n_results=remaining,
                where={
                    "$and": [
                        {"fault_code": {"$eq": fault_code}},
                        {"asset_type": {"$eq": tier_asset_type}},
                    ]
                },
                include=["documents", "metadatas", "distances"],
            )
            ids = raw["ids"][0]
            documents = raw["documents"][0] if raw["documents"] else []
            metadatas = raw["metadatas"][0] if raw["metadatas"] else []
            distances = raw["distances"][0] if raw["distances"] else []
            tier_results: list[StoredSearchResult] = []
            for chunk_id, document, metadata, distance in zip(
                ids, documents, metadatas, distances, strict=True
            ):
                if chunk_id in seen or document is None or metadata is None:
                    continue
                seen.add(chunk_id)
                similarity = max(-1.0, min(1.0, 1.0 - float(distance)))
                tier_results.append(
                    StoredSearchResult(
                        chunk=_chunk_from_chroma(chunk_id, document, metadata),
                        similarity=similarity,
                    )
                )
            results.extend(
                sorted(
                    tier_results,
                    key=lambda item: (-item.similarity, item.chunk.source_id, item.chunk.chunk_id),
                )
            )
        return tuple(results[:n_results])

    def count(self) -> int:
        collection = self._collection_or_none()
        return 0 if collection is None else collection.count()

    def metadata(self) -> dict[str, Any]:
        collection = self._collection_or_none()
        if collection is None:
            raise RetrievalUnavailableError("Prepared knowledge index is not available")
        return dict(collection.metadata or {})

    def _collection_or_none(self) -> Any | None:
        try:
            return self._client.get_collection(
                name=self._collection_name,
                embedding_function=None,
            )
        except Exception as exc:
            if exc.__class__.__name__ in {"NotFoundError", "InvalidCollectionException"}:
                return None
            raise


def _collection_metadata(corpus: KnowledgeCorpus) -> dict[str, str | int]:
    return {
        "knowledge_schema_version": corpus.schema_version,
        "corpus_digest_sha256": corpus.corpus_digest_sha256,
        "embedding_model_id": corpus.embedding_identity.model_id,
        "embedding_model_revision": corpus.embedding_identity.revision,
        "embedding_dimension": corpus.embedding_identity.dimension,
        "distance_metric": DISTANCE_METRIC,
        "chunk_count": len(corpus.chunks),
        "source_count": len(corpus.sources),
    }


def _metadata_matches(actual: dict[str, Any] | None, expected: dict[str, Any]) -> bool:
    if actual is None:
        return False
    return all(actual.get(key) == value for key, value in expected.items())


def _chunk_metadata(chunk: KnowledgeChunk) -> dict[str, str | int]:
    metadata: dict[str, str | int] = {
        "source_id": chunk.source_id,
        "source_digest_sha256": chunk.source_digest_sha256,
        "title": chunk.title,
        "publisher": chunk.publisher,
        "source_uri": chunk.source_uri,
        "section": chunk.section,
        "asset_type": chunk.asset_type,
        "fault_code": chunk.fault_code,
        "source_kind": chunk.source_kind.value,
        "license_or_usage_note": chunk.license_or_usage_note,
        "chunk_index": chunk.chunk_index,
    }
    if chunk.document_version is not None:
        metadata["document_version"] = chunk.document_version
    return metadata


def _chunk_from_chroma(
    chunk_id: str,
    document: str,
    metadata: dict[str, Any],
) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        source_id=str(metadata["source_id"]),
        source_digest_sha256=str(metadata["source_digest_sha256"]),
        title=str(metadata["title"]),
        publisher=str(metadata["publisher"]),
        source_uri=str(metadata["source_uri"]),
        section=str(metadata["section"]),
        text=document,
        asset_type=str(metadata["asset_type"]),
        fault_code=str(metadata["fault_code"]),
        source_kind=KnowledgeSourceKind(str(metadata["source_kind"])),
        license_or_usage_note=str(metadata["license_or_usage_note"]),
        chunk_index=int(metadata["chunk_index"]),
        document_version=(
            str(metadata["document_version"]) if "document_version" in metadata else None
        ),
    )
