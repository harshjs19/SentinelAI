from dataclasses import replace
from typing import cast

from pydantic import TypeAdapter, ValidationError

from backend.app.persistence.errors import ArtifactPersistenceIntegrityError
from domain.entities.analysis import Analysis
from domain.entities.machine import Machine
from modules.copilot.context import CopilotContextBuilder
from modules.copilot.contracts import MaintenanceCopilotRequest
from modules.copilot.report import (
    MaintenanceReport,
    verify_maintenance_report,
    verify_report_digest,
)
from modules.retriever.models import RetrievalBundle, verify_retrieval_bundle_digest
from shared.evidence.models import (
    EvidencePackage,
    snapshot_analysis,
    verify_evidence_package_digest,
)

ANALYSIS_PAYLOAD_SCHEMA_VERSION = "1"

_ANALYSIS_ADAPTER = TypeAdapter(Analysis)
_EVIDENCE_PACKAGE_ADAPTER = TypeAdapter(EvidencePackage)
_RETRIEVAL_BUNDLE_ADAPTER = TypeAdapter(RetrievalBundle)
_MAINTENANCE_REPORT_ADAPTER = TypeAdapter(MaintenanceReport)

JsonPayload = dict[str, object]


def serialize_analysis(analysis: Analysis) -> JsonPayload:
    return _dump_payload(_ANALYSIS_ADAPTER, analysis)


def deserialize_analysis(payload: JsonPayload) -> Analysis:
    return _load_payload(_ANALYSIS_ADAPTER, payload, "Analysis")


def serialize_evidence_package(package: EvidencePackage) -> JsonPayload:
    if not verify_evidence_package_digest(package):
        raise ArtifactPersistenceIntegrityError(
            "Evidence Package failed integrity verification before serialization"
        )
    return _dump_payload(_EVIDENCE_PACKAGE_ADAPTER, package)


def deserialize_evidence_package(payload: JsonPayload) -> EvidencePackage:
    package = _load_payload(_EVIDENCE_PACKAGE_ADAPTER, payload, "Evidence Package")
    package = _restore_top_finding_identity(package)
    if not verify_evidence_package_digest(package):
        raise ArtifactPersistenceIntegrityError(
            "Stored Evidence Package failed digest verification"
        )
    return package


def serialize_retrieval_bundle(bundle: RetrievalBundle) -> JsonPayload:
    if not verify_retrieval_bundle_digest(bundle):
        raise ArtifactPersistenceIntegrityError(
            "Retrieval Bundle failed integrity verification before serialization"
        )
    return _dump_payload(_RETRIEVAL_BUNDLE_ADAPTER, bundle)


def deserialize_retrieval_bundle(payload: JsonPayload) -> RetrievalBundle:
    bundle = _load_payload(_RETRIEVAL_BUNDLE_ADAPTER, payload, "Retrieval Bundle")
    if not verify_retrieval_bundle_digest(bundle):
        raise ArtifactPersistenceIntegrityError(
            "Stored Retrieval Bundle failed digest verification"
        )
    return bundle


def serialize_maintenance_report(report: MaintenanceReport) -> JsonPayload:
    if not verify_report_digest(report):
        raise ArtifactPersistenceIntegrityError(
            "Maintenance Report failed digest verification before serialization"
        )
    return _dump_payload(_MAINTENANCE_REPORT_ADAPTER, report)


def deserialize_maintenance_report(payload: JsonPayload) -> MaintenanceReport:
    report = _load_payload(_MAINTENANCE_REPORT_ADAPTER, payload, "Maintenance Report")
    if not verify_report_digest(report):
        raise ArtifactPersistenceIntegrityError(
            "Stored Maintenance Report failed digest verification"
        )
    return report


def validate_artifact_chain(
    analysis: Analysis,
    evidence_package: EvidencePackage,
    retrieval_bundle: RetrievalBundle,
    maintenance_report: MaintenanceReport,
) -> None:
    if analysis.machine_id != evidence_package.machine.machine_id:
        raise ArtifactPersistenceIntegrityError(
            "Analysis and Evidence Package machine identities do not match"
        )
    if snapshot_analysis(analysis) != evidence_package.analysis:
        raise ArtifactPersistenceIntegrityError(
            "Evidence Package does not contain the exact workflow Analysis"
        )
    if not verify_evidence_package_digest(evidence_package):
        raise ArtifactPersistenceIntegrityError("Evidence Package failed digest verification")
    if not evidence_package.models:
        raise ArtifactPersistenceIntegrityError(
            "Evidence-bearing workflow is missing producing-model provenance"
        )
    if not verify_retrieval_bundle_digest(retrieval_bundle):
        raise ArtifactPersistenceIntegrityError("Retrieval Bundle failed digest verification")
    if (
        retrieval_bundle.evidence_package_id != evidence_package.package_id
        or retrieval_bundle.evidence_package_digest_sha256 != evidence_package.package_digest_sha256
    ):
        raise ArtifactPersistenceIntegrityError(
            "Retrieval Bundle is not bound to the workflow Evidence Package"
        )
    try:
        prepared = CopilotContextBuilder().build(
            MaintenanceCopilotRequest(
                evidence_package=evidence_package,
                retrieval_bundle=retrieval_bundle,
                intent=maintenance_report.request_intent,
            )
        )
    except (TypeError, ValueError) as error:
        raise ArtifactPersistenceIntegrityError(
            "Stored evidence could not reconstruct a valid Copilot context"
        ) from error
    if not verify_maintenance_report(maintenance_report, prepared):
        raise ArtifactPersistenceIntegrityError(
            "Maintenance Report failed workflow-chain verification"
        )


def historical_machine(package: EvidencePackage) -> Machine:
    return Machine(
        id=package.machine.machine_id,
        name=package.machine.name,
        asset_type=package.machine.asset_type,
    )


def _dump_payload[ArtifactT](
    adapter: TypeAdapter[ArtifactT],
    artifact: ArtifactT,
) -> JsonPayload:
    payload = adapter.dump_python(artifact, mode="json")
    if not isinstance(payload, dict):
        raise ArtifactPersistenceIntegrityError(
            "Maintenance artifact serialization did not produce a JSON object"
        )
    return cast(JsonPayload, payload)


def _load_payload[ArtifactT](
    adapter: TypeAdapter[ArtifactT],
    payload: JsonPayload,
    artifact_name: str,
) -> ArtifactT:
    if not isinstance(payload, dict):
        raise ArtifactPersistenceIntegrityError(
            f"Stored {artifact_name} payload is not a JSON object"
        )
    try:
        artifact = adapter.validate_python(payload, strict=False)
    except (ValidationError, TypeError, ValueError) as error:
        raise ArtifactPersistenceIntegrityError(
            f"Stored {artifact_name} payload failed typed reconstruction"
        ) from error
    if _dump_payload(adapter, artifact) != payload:
        raise ArtifactPersistenceIntegrityError(
            f"Stored {artifact_name} payload is not the exact authoritative schema"
        )
    return artifact


def _restore_top_finding_identity(package: EvidencePackage) -> EvidencePackage:
    """Restore the in-memory top-finding references that JSON cannot represent."""
    available = list(enumerate(package.analysis.findings))
    selected_indexes: set[int] = set()
    top_findings = []
    for top_finding in package.analysis.top_findings:
        match = next(
            (
                (index, finding)
                for index, finding in available
                if index not in selected_indexes and finding == top_finding
            ),
            None,
        )
        if match is None:
            raise ArtifactPersistenceIntegrityError(
                "Stored Evidence Package top findings do not reference Analysis findings"
            )
        index, finding = match
        selected_indexes.add(index)
        top_findings.append(finding)
    analysis = replace(package.analysis, top_findings=tuple(top_findings))
    return replace(package, analysis=analysis)
