import hashlib
import hmac
import re
from dataclasses import dataclass
from enum import StrEnum

from modules.retriever.config import RETRIEVAL_BUNDLE_SCHEMA_VERSION
from shared.evidence.canonical import canonical_json_bytes

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class KnowledgeSourceKind(StrEnum):
    EXTERNAL_AUTHORITATIVE = "external_authoritative"
    PROJECT_INTERNAL = "project_internal"


class RetrievalLane(StrEnum):
    INTERPRETATION = "interpretation"
    MAINTENANCE = "maintenance"


@dataclass(frozen=True)
class EmbeddingIdentity:
    model_id: str
    revision: str
    dimension: int

    def __post_init__(self) -> None:
        if not self.model_id.strip() or not self.revision.strip():
            raise ValueError("Embedding model ID and revision cannot be empty")
        if isinstance(self.dimension, bool) or self.dimension <= 0:
            raise ValueError("Embedding dimension must be positive")


@dataclass(frozen=True)
class KnowledgeSource:
    source_id: str
    title: str
    publisher: str
    source_uri: str
    source_kind: KnowledgeSourceKind
    document_path: str
    asset_type: str
    fault_codes: tuple[str, ...]
    version: str
    license_or_usage_note: str
    retrieved_at: str
    notes: str


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    source_id: str
    source_digest_sha256: str
    title: str
    publisher: str
    source_uri: str
    section: str
    text: str
    asset_type: str
    fault_code: str
    source_kind: KnowledgeSourceKind
    license_or_usage_note: str
    chunk_index: int
    document_version: str | None = None


@dataclass(frozen=True)
class RetrievalQuery:
    intent_id: str
    lane: RetrievalLane
    text: str
    fault_code: str
    asset_type: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source_id: str
    title: str
    publisher: str
    source_uri: str
    section: str
    text: str
    fault_code: str
    asset_type: str
    similarity: float
    matched_intent: str
    source_digest_sha256: str

    def __post_init__(self) -> None:
        if not -1.0 <= self.similarity <= 1.0:
            raise ValueError("Cosine retrieval similarity must be between -1 and 1")


@dataclass(frozen=True)
class RetrievalBundle:
    schema_version: str
    evidence_package_id: str
    evidence_package_digest_sha256: str
    corpus_digest_sha256: str
    embedding_model_id: str
    embedding_model_revision: str
    collection_name: str
    queries: tuple[RetrievalQuery, ...]
    chunks: tuple[RetrievedChunk, ...]
    retrieval_bundle_digest_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != RETRIEVAL_BUNDLE_SCHEMA_VERSION:
            raise ValueError(
                f"Retrieval Bundle schema_version must be {RETRIEVAL_BUNDLE_SCHEMA_VERSION}"
            )
        for value in (
            self.evidence_package_digest_sha256,
            self.corpus_digest_sha256,
            self.retrieval_bundle_digest_sha256,
        ):
            if _SHA256_PATTERN.fullmatch(value) is None:
                raise ValueError("Retrieval Bundle digests must be lowercase SHA-256 values")


def create_retrieval_bundle(
    *,
    evidence_package_id: str,
    evidence_package_digest_sha256: str,
    corpus_digest_sha256: str,
    embedding_identity: EmbeddingIdentity,
    collection_name: str,
    queries: tuple[RetrievalQuery, ...],
    chunks: tuple[RetrievedChunk, ...],
) -> RetrievalBundle:
    payload = retrieval_bundle_core_payload(
        evidence_package_id=evidence_package_id,
        evidence_package_digest_sha256=evidence_package_digest_sha256,
        corpus_digest_sha256=corpus_digest_sha256,
        embedding_model_id=embedding_identity.model_id,
        embedding_model_revision=embedding_identity.revision,
        collection_name=collection_name,
        queries=queries,
        chunks=chunks,
    )
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return RetrievalBundle(
        schema_version=RETRIEVAL_BUNDLE_SCHEMA_VERSION,
        evidence_package_id=evidence_package_id,
        evidence_package_digest_sha256=evidence_package_digest_sha256,
        corpus_digest_sha256=corpus_digest_sha256,
        embedding_model_id=embedding_identity.model_id,
        embedding_model_revision=embedding_identity.revision,
        collection_name=collection_name,
        queries=queries,
        chunks=chunks,
        retrieval_bundle_digest_sha256=digest,
    )


def verify_retrieval_bundle_digest(bundle: RetrievalBundle) -> bool:
    expected = hashlib.sha256(
        canonical_json_bytes(
            retrieval_bundle_core_payload(
                evidence_package_id=bundle.evidence_package_id,
                evidence_package_digest_sha256=bundle.evidence_package_digest_sha256,
                corpus_digest_sha256=bundle.corpus_digest_sha256,
                embedding_model_id=bundle.embedding_model_id,
                embedding_model_revision=bundle.embedding_model_revision,
                collection_name=bundle.collection_name,
                queries=bundle.queries,
                chunks=bundle.chunks,
            )
        )
    ).hexdigest()
    return hmac.compare_digest(bundle.retrieval_bundle_digest_sha256, expected)


def retrieval_bundle_payload(bundle: RetrievalBundle) -> dict[str, object]:
    payload = retrieval_bundle_core_payload(
        evidence_package_id=bundle.evidence_package_id,
        evidence_package_digest_sha256=bundle.evidence_package_digest_sha256,
        corpus_digest_sha256=bundle.corpus_digest_sha256,
        embedding_model_id=bundle.embedding_model_id,
        embedding_model_revision=bundle.embedding_model_revision,
        collection_name=bundle.collection_name,
        queries=bundle.queries,
        chunks=bundle.chunks,
    )
    payload["retrieval_bundle_digest_sha256"] = bundle.retrieval_bundle_digest_sha256
    return payload


def retrieval_bundle_core_payload(
    *,
    evidence_package_id: str,
    evidence_package_digest_sha256: str,
    corpus_digest_sha256: str,
    embedding_model_id: str,
    embedding_model_revision: str,
    collection_name: str,
    queries: tuple[RetrievalQuery, ...],
    chunks: tuple[RetrievedChunk, ...],
) -> dict[str, object]:
    return {
        "schema_version": RETRIEVAL_BUNDLE_SCHEMA_VERSION,
        "evidence_package_id": evidence_package_id,
        "evidence_package_digest_sha256": evidence_package_digest_sha256,
        "corpus_digest_sha256": corpus_digest_sha256,
        "embedding": {
            "model_id": embedding_model_id,
            "revision": embedding_model_revision,
        },
        "collection_name": collection_name,
        "queries": [
            {
                "intent_id": query.intent_id,
                "lane": query.lane,
                "text": query.text,
                "fault_code": query.fault_code,
                "asset_type": query.asset_type,
            }
            for query in queries
        ],
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "source_id": chunk.source_id,
                "title": chunk.title,
                "publisher": chunk.publisher,
                "source_uri": chunk.source_uri,
                "section": chunk.section,
                "text": chunk.text,
                "fault_code": chunk.fault_code,
                "asset_type": chunk.asset_type,
                "similarity": chunk.similarity,
                "matched_intent": chunk.matched_intent,
                "source_digest_sha256": chunk.source_digest_sha256,
            }
            for chunk in chunks
        ],
    }
