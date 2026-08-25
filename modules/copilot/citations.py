import re
from dataclasses import dataclass

from modules.copilot.contracts import MaintenanceCopilotRequest
from modules.copilot.exceptions import CopilotInputError, CopilotInputErrorCode
from modules.retriever.models import (
    RetrievalLane,
    RetrievedChunk,
    verify_retrieval_bundle_digest,
)
from shared.evidence.models import verify_evidence_package_digest

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CopilotCitation:
    citation_id: str
    chunk_id: str
    source_id: str
    source_digest_sha256: str
    title: str
    publisher: str
    section: str
    source_uri: str
    fault_code: str
    asset_type: str
    matched_intent: str
    source_lane: RetrievalLane


@dataclass(frozen=True)
class ProviderCitationContext:
    citation_id: str
    title: str
    publisher: str
    section: str
    fault_code: str
    asset_type: str
    source_lane: RetrievalLane
    text: str


@dataclass(frozen=True)
class AssignedCitation:
    citation: CopilotCitation
    provider_context: ProviderCitationContext


def validate_copilot_input(request: MaintenanceCopilotRequest) -> None:
    if not verify_evidence_package_digest(request.evidence_package):
        raise CopilotInputError(CopilotInputErrorCode.INVALID_EVIDENCE_PACKAGE)
    if not verify_retrieval_bundle_digest(request.retrieval_bundle):
        raise CopilotInputError(CopilotInputErrorCode.INVALID_RETRIEVAL_BUNDLE)
    if (
        request.retrieval_bundle.evidence_package_id != request.evidence_package.package_id
        or request.retrieval_bundle.evidence_package_digest_sha256
        != request.evidence_package.package_digest_sha256
    ):
        raise CopilotInputError(CopilotInputErrorCode.EVIDENCE_RETRIEVAL_MISMATCH)
    for chunk in request.retrieval_bundle.chunks:
        if not _has_complete_citation_metadata(chunk):
            raise CopilotInputError(CopilotInputErrorCode.INCOMPLETE_CITATION_METADATA)


def assign_citations(request: MaintenanceCopilotRequest) -> tuple[AssignedCitation, ...]:
    validate_copilot_input(request)
    lanes_by_intent = {query.intent_id: query.lane for query in request.retrieval_bundle.queries}
    assigned: list[AssignedCitation] = []
    for index, chunk in enumerate(request.retrieval_bundle.chunks, start=1):
        try:
            lane = lanes_by_intent[chunk.matched_intent]
        except KeyError as error:
            raise CopilotInputError(CopilotInputErrorCode.INVALID_RETRIEVAL_BUNDLE) from error
        citation_id = f"K{index}"
        assigned.append(
            AssignedCitation(
                citation=CopilotCitation(
                    citation_id=citation_id,
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.source_id,
                    source_digest_sha256=chunk.source_digest_sha256,
                    title=chunk.title,
                    publisher=chunk.publisher,
                    section=chunk.section,
                    source_uri=chunk.source_uri,
                    fault_code=chunk.fault_code,
                    asset_type=chunk.asset_type,
                    matched_intent=chunk.matched_intent,
                    source_lane=lane,
                ),
                provider_context=ProviderCitationContext(
                    citation_id=citation_id,
                    title=chunk.title,
                    publisher=chunk.publisher,
                    section=chunk.section,
                    fault_code=chunk.fault_code,
                    asset_type=chunk.asset_type,
                    source_lane=lane,
                    text=chunk.text,
                ),
            )
        )
    return tuple(assigned)


def _has_complete_citation_metadata(chunk: RetrievedChunk) -> bool:
    required = (
        chunk.chunk_id,
        chunk.source_id,
        chunk.title,
        chunk.publisher,
        chunk.section,
        chunk.source_uri,
        chunk.fault_code,
        chunk.asset_type,
        chunk.matched_intent,
    )
    return all(value.strip() for value in required) and bool(
        _SHA256_PATTERN.fullmatch(chunk.source_digest_sha256)
    )
