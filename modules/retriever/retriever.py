from dataclasses import dataclass

from modules.retriever.config import MAXIMUM_TOTAL_CHUNKS, TOP_K_PER_INTENT
from modules.retriever.embedding import TextEmbedder
from modules.retriever.exceptions import InvalidEvidencePackageError
from modules.retriever.models import (
    RetrievalBundle,
    RetrievalQuery,
    RetrievedChunk,
    create_retrieval_bundle,
)
from modules.retriever.planner import RetrievalQueryPlanner
from modules.retriever.store import ChromaKnowledgeStore
from shared.evidence.models import EvidencePackage, verify_evidence_package_digest


@dataclass(frozen=True)
class _Candidate:
    query_index: int
    chunk: RetrievedChunk


class KnowledgeRetriever:
    def __init__(
        self,
        *,
        store: ChromaKnowledgeStore,
        embedder: TextEmbedder,
        corpus_digest_sha256: str,
        planner: RetrievalQueryPlanner | None = None,
        top_k_per_intent: int = TOP_K_PER_INTENT,
        maximum_total_chunks: int = MAXIMUM_TOTAL_CHUNKS,
    ) -> None:
        if top_k_per_intent <= 0 or maximum_total_chunks <= 0:
            raise ValueError("Retriever result limits must be positive")
        self._store = store
        self._embedder = embedder
        self._corpus_digest_sha256 = corpus_digest_sha256
        self._planner = planner or RetrievalQueryPlanner()
        self._top_k_per_intent = top_k_per_intent
        self._maximum_total_chunks = maximum_total_chunks

    def retrieve(self, evidence_package: EvidencePackage) -> RetrievalBundle:
        if not verify_evidence_package_digest(evidence_package):
            raise InvalidEvidencePackageError(
                "Evidence Package digest verification failed; retrieval was rejected"
            )
        self._store.validate_identity(
            corpus_digest_sha256=self._corpus_digest_sha256,
            embedding_identity=self._embedder.identity,
        )
        queries = self._planner.plan(evidence_package)
        candidates: list[_Candidate] = []
        for query_index, query in enumerate(queries):
            query_embedding = self._embedder.embed_query(query.text)
            matches = self._store.query_tiered(
                query_embedding,
                fault_code=query.fault_code,
                asset_type=query.asset_type,
                n_results=self._top_k_per_intent,
                embedding_dimension=self._embedder.identity.dimension,
            )
            candidates.extend(
                _Candidate(
                    query_index=query_index,
                    chunk=_retrieved_chunk(match.chunk, match.similarity, query),
                )
                for match in matches
            )
        chunks = _deduplicate_and_order(candidates, self._maximum_total_chunks)
        return create_retrieval_bundle(
            evidence_package_id=evidence_package.package_id,
            evidence_package_digest_sha256=evidence_package.package_digest_sha256,
            corpus_digest_sha256=self._corpus_digest_sha256,
            embedding_identity=self._embedder.identity,
            collection_name=self._store.collection_name,
            queries=queries,
            chunks=chunks,
        )


def _retrieved_chunk(chunk: object, similarity: float, query: RetrievalQuery) -> RetrievedChunk:
    from modules.retriever.models import KnowledgeChunk

    if not isinstance(chunk, KnowledgeChunk):
        raise TypeError("Knowledge store returned an invalid chunk")
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        source_id=chunk.source_id,
        title=chunk.title,
        publisher=chunk.publisher,
        source_uri=chunk.source_uri,
        section=chunk.section,
        text=chunk.text,
        fault_code=chunk.fault_code,
        asset_type=chunk.asset_type,
        similarity=similarity,
        matched_intent=query.intent_id,
        source_digest_sha256=chunk.source_digest_sha256,
    )


def _deduplicate_and_order(
    candidates: list[_Candidate],
    maximum_total_chunks: int,
) -> tuple[RetrievedChunk, ...]:
    best_by_chunk: dict[str, _Candidate] = {}
    for candidate in candidates:
        current = best_by_chunk.get(candidate.chunk.chunk_id)
        candidate_key = (
            -candidate.chunk.similarity,
            candidate.query_index,
            candidate.chunk.source_id,
            candidate.chunk.chunk_id,
        )
        if current is None:
            best_by_chunk[candidate.chunk.chunk_id] = candidate
            continue
        current_key = (
            -current.chunk.similarity,
            current.query_index,
            current.chunk.source_id,
            current.chunk.chunk_id,
        )
        if candidate_key < current_key:
            best_by_chunk[candidate.chunk.chunk_id] = candidate
    ordered = sorted(
        best_by_chunk.values(),
        key=lambda item: (
            item.query_index,
            -item.chunk.similarity,
            item.chunk.source_id,
            item.chunk.chunk_id,
        ),
    )
    return tuple(item.chunk for item in ordered[:maximum_total_chunks])
