import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from ai_core.model_capabilities import (
    ModelLifecycleStatus,
    validate_evaluation_reference,
    validate_model_id,
)
from ai_core.model_provenance import ProducingModelContext
from domain.entities.analysis import Analysis
from domain.entities.finding import Finding
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.modality import Modality
from domain.enums.risk_level import RiskLevel
from shared.evidence.canonical import canonical_json_bytes
from shared.evidence.provenance import SourceKind, SourceProvenance

SCHEMA_VERSION = "1"
PACKAGE_ID_DIGEST_CHARACTERS = 32
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class MachineSnapshot:
    machine_id: UUID
    name: str
    asset_type: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Machine snapshot name cannot be empty")
        if not self.asset_type.strip():
            raise ValueError("Machine snapshot asset_type cannot be empty")


@dataclass(frozen=True)
class AnalysisSnapshot:
    analysis_id: UUID
    machine_id: UUID
    predictions: tuple[Prediction, ...]
    findings: tuple[Finding, ...]
    condition: ConditionState
    status: AnalysisStatus
    health_score: float | None
    risk_level: RiskLevel | None
    limitations: tuple[AnalysisLimitation, ...]
    created_at: datetime
    top_findings: tuple[Finding, ...]

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() != timedelta(0):
            raise ValueError("Analysis snapshot created_at must be timezone-aware UTC")


@dataclass(frozen=True)
class ModelProvenance:
    model_id: str
    modality: Modality
    status: ModelLifecycleStatus
    runtime_default: bool
    validated_scope: str
    evaluation_reference: str
    confidence_semantics: str

    def __post_init__(self) -> None:
        validate_model_id(self.model_id)
        if not self.validated_scope.strip():
            raise ValueError("Model provenance validated_scope cannot be empty")
        if not self.confidence_semantics.strip():
            raise ValueError("Model provenance confidence_semantics cannot be empty")
        if self.status is ModelLifecycleStatus.REJECTED_EXPERIMENT:
            raise ValueError("Rejected model capability cannot be Evidence Package provenance")
        validate_evaluation_reference(self.evaluation_reference)


@dataclass(frozen=True)
class EvidenceClaimSupport:
    condition_available: bool
    failure_probability_available: bool
    fault_severity_available: bool
    health_score_available: bool
    operational_risk_available: bool


@dataclass(frozen=True)
class EvidencePackage:
    schema_version: str
    package_id: str
    package_digest_sha256: str
    created_at: datetime
    machine: MachineSnapshot
    analysis: AnalysisSnapshot
    sources: tuple[SourceProvenance, ...]
    models: tuple[ModelProvenance, ...]
    claim_support: EvidenceClaimSupport

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Evidence Package schema_version must be {SCHEMA_VERSION}")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() != timedelta(0):
            raise ValueError("Evidence Package created_at must be timezone-aware UTC")
        if self.created_at != self.analysis.created_at:
            raise ValueError("Evidence Package created_at must equal Analysis created_at")
        if self.machine.machine_id != self.analysis.machine_id:
            raise ValueError("Evidence Package Machine and Analysis IDs must match")
        if _SHA256_PATTERN.fullmatch(self.package_digest_sha256) is None:
            raise ValueError("Evidence Package digest must be 64 lowercase hexadecimal digits")
        if self.package_id != package_id_from_digest(self.package_digest_sha256):
            raise ValueError("Evidence Package ID does not match its digest")
        _validate_provenance_modalities(self.analysis, self.sources, self.models)
        _validate_claim_support(self.analysis, self.claim_support)


def snapshot_machine(machine: Machine) -> MachineSnapshot:
    return MachineSnapshot(
        machine_id=machine.id,
        name=machine.name,
        asset_type=machine.asset_type,
    )


def snapshot_analysis(analysis: Analysis) -> AnalysisSnapshot:
    return AnalysisSnapshot(
        analysis_id=analysis.id,
        machine_id=analysis.machine_id,
        predictions=tuple(analysis.predictions),
        findings=tuple(analysis.findings),
        condition=analysis.condition,
        status=analysis.status,
        health_score=None if analysis.health_score is None else analysis.health_score.value,
        risk_level=analysis.risk_level,
        limitations=tuple(analysis.limitations),
        created_at=analysis.created_at,
        top_findings=tuple(analysis.top_findings),
    )


def snapshot_model(context: ProducingModelContext) -> ModelProvenance:
    return ModelProvenance(
        model_id=str(context.model_id),
        modality=context.modality,
        status=context.lifecycle_status,
        runtime_default=bool(context.runtime_default_at_execution),
        validated_scope=str(context.validated_scope),
        evaluation_reference=str(context.evaluation_reference),
        confidence_semantics=str(context.confidence_semantics),
    )


def claim_support_for_analysis(analysis: AnalysisSnapshot) -> EvidenceClaimSupport:
    return EvidenceClaimSupport(
        condition_available=analysis.status is not AnalysisStatus.INSUFFICIENT_EVIDENCE,
        failure_probability_available=False,
        fault_severity_available=False,
        health_score_available=analysis.health_score is not None,
        operational_risk_available=analysis.risk_level is not None,
    )


def create_evidence_package(
    machine: MachineSnapshot,
    analysis: AnalysisSnapshot,
    sources: tuple[SourceProvenance, ...],
    models: tuple[ModelProvenance, ...],
    claim_support: EvidenceClaimSupport,
) -> EvidencePackage:
    sorted_sources = tuple(sorted(sources, key=lambda source: source.modality.value))
    sorted_models = tuple(sorted(models, key=lambda model: (model.modality.value, model.model_id)))
    core_payload = evidence_package_core_payload(
        schema_version=SCHEMA_VERSION,
        created_at=analysis.created_at,
        machine=machine,
        analysis=analysis,
        sources=sorted_sources,
        models=sorted_models,
        claim_support=claim_support,
    )
    digest = hashlib.sha256(canonical_json_bytes(core_payload)).hexdigest()
    return EvidencePackage(
        schema_version=SCHEMA_VERSION,
        package_id=package_id_from_digest(digest),
        package_digest_sha256=digest,
        created_at=analysis.created_at,
        machine=machine,
        analysis=analysis,
        sources=sorted_sources,
        models=sorted_models,
        claim_support=claim_support,
    )


def verify_evidence_package_digest(package: EvidencePackage) -> bool:
    expected_digest = hashlib.sha256(
        canonical_json_bytes(
            evidence_package_core_payload(
                schema_version=package.schema_version,
                created_at=package.created_at,
                machine=package.machine,
                analysis=package.analysis,
                sources=package.sources,
                models=package.models,
                claim_support=package.claim_support,
            )
        )
    ).hexdigest()
    expected_id = package_id_from_digest(expected_digest)
    return hmac.compare_digest(
        package.package_digest_sha256, expected_digest
    ) and hmac.compare_digest(package.package_id, expected_id)


def package_id_from_digest(digest: str) -> str:
    if _SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError("Evidence Package digest must be 64 lowercase hexadecimal digits")
    return f"evp1_{digest[:PACKAGE_ID_DIGEST_CHARACTERS]}"


def evidence_package_core_payload(
    *,
    schema_version: str,
    created_at: datetime,
    machine: MachineSnapshot,
    analysis: AnalysisSnapshot,
    sources: tuple[SourceProvenance, ...],
    models: tuple[ModelProvenance, ...],
    claim_support: EvidenceClaimSupport,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "created_at": created_at,
        "machine": _machine_payload(machine),
        "analysis": _analysis_payload(analysis),
        "sources": [_source_payload(source) for source in sources],
        "models": [_model_payload(model) for model in models],
        "claim_support": _claim_support_payload(claim_support),
    }


def _machine_payload(machine: MachineSnapshot) -> dict[str, object]:
    return {
        "machine_id": machine.machine_id,
        "name": machine.name,
        "asset_type": machine.asset_type,
    }


def _prediction_payload(prediction: Prediction) -> dict[str, object]:
    return {
        "modality": prediction.modality,
        "label": prediction.label,
        "confidence": prediction.confidence,
    }


def _finding_payload(finding: Finding) -> dict[str, object]:
    return {
        "modality": finding.modality,
        "code": finding.code,
        "condition": finding.condition,
        "confidence": finding.confidence,
        "confidence_kind": finding.confidence_kind,
    }


def _analysis_payload(analysis: AnalysisSnapshot) -> dict[str, object]:
    return {
        "analysis_id": analysis.analysis_id,
        "machine_id": analysis.machine_id,
        "predictions": [_prediction_payload(item) for item in analysis.predictions],
        "findings": [_finding_payload(item) for item in analysis.findings],
        "condition": analysis.condition,
        "status": analysis.status,
        "health_score": analysis.health_score,
        "risk_level": analysis.risk_level,
        "limitations": list(analysis.limitations),
        "created_at": analysis.created_at,
        "top_findings": [_finding_payload(item) for item in analysis.top_findings],
    }


def _source_payload(source: SourceProvenance) -> dict[str, object]:
    return {
        "modality": source.modality,
        "source_kind": source.source_kind,
        "sha256": source.sha256,
        "size_bytes": source.size_bytes,
        "content_type": source.content_type,
    }


def _model_payload(model: ModelProvenance) -> dict[str, object]:
    return {
        "model_id": model.model_id,
        "modality": model.modality,
        "status": model.status,
        "runtime_default": model.runtime_default,
        "validated_scope": model.validated_scope,
        "evaluation_reference": model.evaluation_reference,
        "confidence_semantics": model.confidence_semantics,
    }


def _claim_support_payload(claim_support: EvidenceClaimSupport) -> dict[str, object]:
    return {
        "condition_available": claim_support.condition_available,
        "failure_probability_available": claim_support.failure_probability_available,
        "fault_severity_available": claim_support.fault_severity_available,
        "health_score_available": claim_support.health_score_available,
        "operational_risk_available": claim_support.operational_risk_available,
    }


def _validate_provenance_modalities(
    analysis: AnalysisSnapshot,
    sources: tuple[SourceProvenance, ...],
    models: tuple[ModelProvenance, ...],
) -> None:
    prediction_modalities = [prediction.modality for prediction in analysis.predictions]
    source_modalities = [source.modality for source in sources]
    model_modalities = [model.modality for model in models]
    if len(set(prediction_modalities)) != len(prediction_modalities):
        raise ValueError("Evidence Package Analysis contains duplicate prediction modalities")
    if len(set(source_modalities)) != len(source_modalities):
        raise ValueError("Evidence Package contains duplicate source modalities")
    if len(set(model_modalities)) != len(model_modalities):
        raise ValueError("Evidence Package contains duplicate model modalities")
    if set(source_modalities) != set(prediction_modalities):
        raise ValueError("Evidence Package source modalities must match Analysis predictions")
    if set(model_modalities) != set(prediction_modalities):
        raise ValueError("Evidence Package model modalities must match Analysis predictions")
    for source in sources:
        expected_kind = (
            SourceKind.STRUCTURED if source.modality is Modality.TIMESERIES else SourceKind.FILE
        )
        if source.source_kind is not expected_kind:
            raise ValueError(
                f"Evidence Package {source.modality.value} source must use "
                f"{expected_kind.value} provenance"
            )
    if source_modalities != sorted(source_modalities, key=lambda modality: modality.value):
        raise ValueError("Evidence Package sources must use deterministic modality ordering")
    if models != tuple(sorted(models, key=lambda model: (model.modality.value, model.model_id))):
        raise ValueError("Evidence Package models must use deterministic ordering")


def _validate_claim_support(
    analysis: AnalysisSnapshot,
    claim_support: EvidenceClaimSupport,
) -> None:
    expected = claim_support_for_analysis(analysis)
    if claim_support != expected:
        raise ValueError("Evidence Package claim support is inconsistent with Analysis")
