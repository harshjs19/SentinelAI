import hashlib
import math
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from backend.app.services.evidence_package_service import EvidencePackageService
from domain.entities.analysis import Analysis
from domain.entities.finding import Finding
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from modules.retriever.embedding import EmbeddingVector
from modules.retriever.models import EmbeddingIdentity
from shared.evidence.models import EvidencePackage
from shared.evidence.provenance import file_source_provenance, structured_source_provenance

FAKE_IDENTITY = EmbeddingIdentity("fake/test-embedder", "test-revision", 8)


class FakeEmbedder:
    def __init__(self, identity: EmbeddingIdentity = FAKE_IDENTITY) -> None:
        self._identity = identity

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    def embed_documents(self, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]:
        return tuple(self._embed(text) for text in texts)

    def embed_query(self, text: str) -> EmbeddingVector:
        return self._embed(text)

    def _embed(self, text: str) -> EmbeddingVector:
        values = [0.0] * self._identity.dimension
        for token in re.findall(r"[a-z0-9_]+", text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:2], "big") % len(values)
            values[index] += 1.0
        if not any(values):
            values[0] = 1.0
        norm = math.sqrt(sum(value * value for value in values))
        return tuple(value / norm for value in values)


def make_evidence_package(
    code: str | None,
    *,
    modality: Modality = Modality.TIMESERIES,
    asset_type: str = "rotating_electromechanical_system",
) -> EvidencePackage:
    machine_id = UUID("00000000-0000-0000-0000-000000009001")
    machine = Machine(machine_id, "Retriever fixture", asset_type)
    created_at = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)
    if code is None:
        analysis = Analysis(
            id=UUID("00000000-0000-0000-0000-000000009002"),
            machine_id=machine_id,
            predictions=(),
            findings=(),
            condition=ConditionState.INDETERMINATE,
            status=AnalysisStatus.INSUFFICIENT_EVIDENCE,
            health_score=None,
            risk_level=None,
            limitations=(),
            created_at=created_at,
        )
        return EvidencePackageService().build(machine, analysis, [])

    condition = ConditionState.NORMAL if code == "healthy" else ConditionState.ABNORMAL
    prediction = Prediction(modality, code, 0.84)
    finding = Finding(modality, code, condition, 0.84, ConfidenceKind.RAW)
    limitations = [
        AnalysisLimitation.UNCALIBRATED_CONFIDENCE,
        AnalysisLimitation.RISK_CONTEXT_UNAVAILABLE,
        AnalysisLimitation.SINGLE_MODALITY_EVIDENCE,
    ]
    if condition is ConditionState.ABNORMAL:
        limitations.insert(1, AnalysisLimitation.FAULT_SEVERITY_UNAVAILABLE)
    analysis = Analysis(
        id=UUID("00000000-0000-0000-0000-000000009002"),
        machine_id=machine_id,
        predictions=(prediction,),
        findings=(finding,),
        condition=condition,
        status=AnalysisStatus.PROVISIONAL,
        health_score=None,
        risk_level=None,
        limitations=tuple(limitations),
        created_at=created_at,
    )
    if modality is Modality.TIMESERIES:
        source = structured_source_provenance(modality, {"samples": [{"value": 1.0}]})
    else:
        media_types = {
            Modality.AUDIO: "audio/wav",
            Modality.VISION: "image/png",
            Modality.THERMAL: "image/png",
        }
        source = file_source_provenance(modality, b"private fixture bytes", media_types[modality])
    return EvidencePackageService().build(machine, analysis, [source])
