from dataclasses import dataclass

from domain.enums.modality import Modality
from modules.copilot.context import CopilotContextBuilder, PreparedCopilotRequest
from modules.copilot.contracts import CopilotIntent, MaintenanceCopilotRequest
from modules.retriever.models import (
    EmbeddingIdentity,
    RetrievalBundle,
    RetrievalLane,
    RetrievalQuery,
    RetrievedChunk,
    create_retrieval_bundle,
)
from shared.evidence.models import EvidencePackage
from tests.retriever.support import make_evidence_package

CORPUS_DIGEST = "c" * 64
SOURCE_DIGEST = "d" * 64
EMBEDDING_IDENTITY = EmbeddingIdentity("fake/copilot-embedder", "test-revision", 8)


@dataclass(frozen=True)
class ChunkSpec:
    fault_code: str
    lane: RetrievalLane = RetrievalLane.MAINTENANCE
    asset_type: str = "rotating_electromechanical_system"
    text: str = "Synthetic source-backed condition interpretation."
    title: str = "Synthetic maintenance reference"
    publisher: str = "SentinelAI tests"
    section: str = "Condition interpretation"
    source_uri: str = "https://example.invalid/synthetic-reference"
    source_digest_sha256: str = SOURCE_DIGEST


def make_bundle(
    package: EvidencePackage,
    specs: tuple[ChunkSpec, ...],
) -> RetrievalBundle:
    queries: list[RetrievalQuery] = []
    chunks: list[RetrievedChunk] = []
    for index, spec in enumerate(specs, start=1):
        intent_id = f"{spec.lane.value}:{spec.fault_code}:{index}"
        queries.append(
            RetrievalQuery(
                intent_id=intent_id,
                lane=spec.lane,
                text=f"synthetic query {spec.fault_code}",
                fault_code=spec.fault_code,
                asset_type=package.machine.asset_type,
            )
        )
        chunks.append(
            RetrievedChunk(
                chunk_id=f"chunk-{index}",
                source_id=f"source-{index}",
                title=spec.title,
                publisher=spec.publisher,
                source_uri=spec.source_uri,
                section=spec.section,
                text=spec.text,
                fault_code=spec.fault_code,
                asset_type=spec.asset_type,
                similarity=0.9 - (index * 0.01),
                matched_intent=intent_id,
                source_digest_sha256=spec.source_digest_sha256,
            )
        )
    return create_retrieval_bundle(
        evidence_package_id=package.package_id,
        evidence_package_digest_sha256=package.package_digest_sha256,
        corpus_digest_sha256=CORPUS_DIGEST,
        embedding_identity=EMBEDDING_IDENTITY,
        collection_name="copilot_test_collection",
        queries=tuple(queries),
        chunks=tuple(chunks),
    )


def make_prepared(
    code: str | None = "bearing_fault",
    *,
    modality: Modality = Modality.TIMESERIES,
    intent: CopilotIntent = CopilotIntent.EXPLAIN_FINDING,
    specs: tuple[ChunkSpec, ...] | None = None,
    question: str | None = None,
    asset_type: str = "rotating_electromechanical_system",
) -> PreparedCopilotRequest:
    package = make_evidence_package(code, modality=modality, asset_type=asset_type)
    if specs is None:
        specs = () if code is None else (ChunkSpec(code, asset_type=asset_type),)
    request = MaintenanceCopilotRequest(
        evidence_package=package,
        retrieval_bundle=make_bundle(package, specs),
        intent=intent,
        question=question,
    )
    return CopilotContextBuilder().build(request)
