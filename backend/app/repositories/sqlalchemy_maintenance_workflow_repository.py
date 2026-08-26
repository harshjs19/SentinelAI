from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.maintenance_artifacts import (
    AnalysisModel,
    EvidencePackageModel,
    MaintenanceReportModel,
    RetrievalBundleModel,
)
from backend.app.persistence.errors import (
    ArtifactIdentityConflictError,
    ArtifactPersistenceIntegrityError,
)
from backend.app.persistence.maintenance_artifact_mapper import (
    ANALYSIS_PAYLOAD_SCHEMA_VERSION,
    deserialize_analysis,
    deserialize_evidence_package,
    deserialize_maintenance_report,
    deserialize_retrieval_bundle,
    historical_machine,
    serialize_analysis,
    serialize_evidence_package,
    serialize_maintenance_report,
    serialize_retrieval_bundle,
    validate_artifact_chain,
)
from backend.app.repositories.maintenance_workflow_repository import (
    HistoricalMaintenanceWorkflow,
)
from domain.entities.analysis import Analysis
from modules.copilot.report import MaintenanceReport
from modules.retriever.models import RetrievalBundle
from shared.evidence.models import EvidencePackage


class SQLAlchemyMaintenanceWorkflowRepository:
    """Append-only storage for one complete maintenance artifact chain.

    Methods flush staged writes so database constraints are checked, but transaction
    commit and rollback remain the responsibility of the surrounding session boundary.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_analysis(self, analysis: Analysis) -> None:
        payload = serialize_analysis(analysis)
        existing = await self._session.get(AnalysisModel, analysis.id)
        expected = {
            "machine_id": analysis.machine_id,
            "condition": analysis.condition.value,
            "status": analysis.status.value,
            "created_at": analysis.created_at,
            "payload_schema_version": ANALYSIS_PAYLOAD_SCHEMA_VERSION,
            "payload": payload,
        }
        if existing is not None:
            _require_exact_replay("Analysis", analysis.id, existing, expected)
            return
        self._session.add(
            AnalysisModel(
                id=analysis.id,
                machine_id=analysis.machine_id,
                condition=analysis.condition.value,
                status=analysis.status.value,
                created_at=analysis.created_at,
                payload_schema_version=ANALYSIS_PAYLOAD_SCHEMA_VERSION,
                payload=payload,
            )
        )
        await self._session.flush()

    async def save_evidence_package(self, package: EvidencePackage) -> None:
        payload = serialize_evidence_package(package)
        existing = await self._session.get(EvidencePackageModel, package.package_id)
        expected = {
            "package_digest_sha256": package.package_digest_sha256,
            "machine_id": package.machine.machine_id,
            "analysis_id": package.analysis.analysis_id,
            "created_at": package.created_at,
            "schema_version": package.schema_version,
            "payload": payload,
        }
        if existing is not None:
            _require_exact_replay("Evidence Package", package.package_id, existing, expected)
            return
        digest_owner = await self._session.scalar(
            select(EvidencePackageModel).where(
                EvidencePackageModel.package_digest_sha256 == package.package_digest_sha256
            )
        )
        if digest_owner is not None:
            raise ArtifactIdentityConflictError(
                "Evidence Package digest is already bound to a different identity"
            )
        self._session.add(
            EvidencePackageModel(
                package_id=package.package_id,
                package_digest_sha256=package.package_digest_sha256,
                machine_id=package.machine.machine_id,
                analysis_id=package.analysis.analysis_id,
                created_at=package.created_at,
                schema_version=package.schema_version,
                payload=payload,
            )
        )
        await self._session.flush()

    async def save_retrieval_bundle(self, bundle: RetrievalBundle) -> None:
        payload = serialize_retrieval_bundle(bundle)
        identity = bundle.retrieval_bundle_digest_sha256
        existing = await self._session.get(RetrievalBundleModel, identity)
        expected = {
            "evidence_package_id": bundle.evidence_package_id,
            "evidence_package_digest_sha256": bundle.evidence_package_digest_sha256,
            "corpus_digest_sha256": bundle.corpus_digest_sha256,
            "embedding_model_id": bundle.embedding_model_id,
            "embedding_model_revision": bundle.embedding_model_revision,
            "schema_version": bundle.schema_version,
            "payload": payload,
        }
        if existing is not None:
            _require_exact_replay("Retrieval Bundle", identity, existing, expected)
            return
        self._session.add(
            RetrievalBundleModel(
                retrieval_bundle_digest_sha256=identity,
                evidence_package_id=bundle.evidence_package_id,
                evidence_package_digest_sha256=bundle.evidence_package_digest_sha256,
                corpus_digest_sha256=bundle.corpus_digest_sha256,
                embedding_model_id=bundle.embedding_model_id,
                embedding_model_revision=bundle.embedding_model_revision,
                schema_version=bundle.schema_version,
                payload=payload,
            )
        )
        await self._session.flush()

    async def save_maintenance_report(self, report: MaintenanceReport) -> None:
        payload = serialize_maintenance_report(report)
        existing = await self._session.get(MaintenanceReportModel, report.report_id)
        expected = {
            "report_digest_sha256": report.report_digest_sha256,
            "machine_id": report.machine.machine_id,
            "evidence_package_id": report.evidence_reference.package_id,
            "evidence_package_digest_sha256": report.evidence_reference.package_digest_sha256,
            "retrieval_bundle_digest_sha256": (
                report.retrieval_reference.retrieval_bundle_digest_sha256
            ),
            "generation_status": report.generation_status.value,
            "generated_at": report.generated_at,
            "schema_version": report.schema_version,
            "payload": payload,
        }
        if existing is not None:
            _require_exact_replay("Maintenance Report", report.report_id, existing, expected)
            return
        digest_owner = await self._session.scalar(
            select(MaintenanceReportModel).where(
                MaintenanceReportModel.report_digest_sha256 == report.report_digest_sha256
            )
        )
        if digest_owner is not None:
            raise ArtifactIdentityConflictError(
                "Maintenance Report digest is already bound to a different identity"
            )
        self._session.add(
            MaintenanceReportModel(
                report_id=report.report_id,
                report_digest_sha256=report.report_digest_sha256,
                machine_id=report.machine.machine_id,
                evidence_package_id=report.evidence_reference.package_id,
                evidence_package_digest_sha256=report.evidence_reference.package_digest_sha256,
                retrieval_bundle_digest_sha256=(
                    report.retrieval_reference.retrieval_bundle_digest_sha256
                ),
                generation_status=report.generation_status.value,
                generated_at=report.generated_at,
                schema_version=report.schema_version,
                payload=payload,
            )
        )
        await self._session.flush()

    async def get_by_report_id(
        self,
        report_id: UUID,
    ) -> HistoricalMaintenanceWorkflow | None:
        report_model = await self._session.get(MaintenanceReportModel, report_id)
        if report_model is None:
            return None

        retrieval_model = await self._session.get(
            RetrievalBundleModel,
            report_model.retrieval_bundle_digest_sha256,
        )
        if retrieval_model is None:
            raise ArtifactPersistenceIntegrityError(
                "Stored Maintenance Report has no Retrieval Bundle"
            )
        evidence_model = await self._session.get(
            EvidencePackageModel,
            report_model.evidence_package_id,
        )
        if evidence_model is None:
            raise ArtifactPersistenceIntegrityError(
                "Stored Maintenance Report has no Evidence Package"
            )
        analysis_model = await self._session.get(
            AnalysisModel,
            evidence_model.analysis_id,
        )
        if analysis_model is None:
            raise ArtifactPersistenceIntegrityError("Stored Evidence Package has no Analysis")

        analysis = _load_analysis(analysis_model)
        package = _load_evidence_package(evidence_model)
        bundle = _load_retrieval_bundle(retrieval_model)
        report = _load_maintenance_report(report_model)
        validate_artifact_chain(analysis, package, bundle, report)
        return HistoricalMaintenanceWorkflow(
            machine=historical_machine(package),
            analysis=analysis,
            evidence_package=package,
            retrieval_bundle=bundle,
            maintenance_report=report,
        )

    async def list_for_machine(
        self,
        machine_id: UUID,
    ) -> list[HistoricalMaintenanceWorkflow]:
        report_ids = await self._session.scalars(
            select(MaintenanceReportModel.report_id)
            .where(MaintenanceReportModel.machine_id == machine_id)
            .order_by(
                MaintenanceReportModel.generated_at.desc(),
                MaintenanceReportModel.report_id.desc(),
            )
        )
        workflows: list[HistoricalMaintenanceWorkflow] = []
        for report_id in report_ids:
            workflow = await self.get_by_report_id(report_id)
            if workflow is None:
                raise ArtifactPersistenceIntegrityError(
                    "Maintenance Report disappeared during historical listing"
                )
            workflows.append(workflow)
        return workflows


def _load_analysis(model: AnalysisModel) -> Analysis:
    analysis = deserialize_analysis(model.payload)
    _require_stored_metadata(
        "Analysis",
        {
            "id": (model.id, analysis.id),
            "machine_id": (model.machine_id, analysis.machine_id),
            "condition": (model.condition, analysis.condition.value),
            "status": (model.status, analysis.status.value),
            "created_at": (model.created_at, analysis.created_at),
            "payload_schema_version": (
                model.payload_schema_version,
                ANALYSIS_PAYLOAD_SCHEMA_VERSION,
            ),
        },
    )
    return analysis


def _load_evidence_package(model: EvidencePackageModel) -> EvidencePackage:
    package = deserialize_evidence_package(model.payload)
    _require_stored_metadata(
        "Evidence Package",
        {
            "package_id": (model.package_id, package.package_id),
            "package_digest_sha256": (
                model.package_digest_sha256,
                package.package_digest_sha256,
            ),
            "machine_id": (model.machine_id, package.machine.machine_id),
            "analysis_id": (model.analysis_id, package.analysis.analysis_id),
            "created_at": (model.created_at, package.created_at),
            "schema_version": (model.schema_version, package.schema_version),
        },
    )
    return package


def _load_retrieval_bundle(model: RetrievalBundleModel) -> RetrievalBundle:
    bundle = deserialize_retrieval_bundle(model.payload)
    _require_stored_metadata(
        "Retrieval Bundle",
        {
            "retrieval_bundle_digest_sha256": (
                model.retrieval_bundle_digest_sha256,
                bundle.retrieval_bundle_digest_sha256,
            ),
            "evidence_package_id": (
                model.evidence_package_id,
                bundle.evidence_package_id,
            ),
            "evidence_package_digest_sha256": (
                model.evidence_package_digest_sha256,
                bundle.evidence_package_digest_sha256,
            ),
            "corpus_digest_sha256": (
                model.corpus_digest_sha256,
                bundle.corpus_digest_sha256,
            ),
            "embedding_model_id": (model.embedding_model_id, bundle.embedding_model_id),
            "embedding_model_revision": (
                model.embedding_model_revision,
                bundle.embedding_model_revision,
            ),
            "schema_version": (model.schema_version, bundle.schema_version),
        },
    )
    return bundle


def _load_maintenance_report(model: MaintenanceReportModel) -> MaintenanceReport:
    report = deserialize_maintenance_report(model.payload)
    _require_stored_metadata(
        "Maintenance Report",
        {
            "report_id": (model.report_id, report.report_id),
            "report_digest_sha256": (
                model.report_digest_sha256,
                report.report_digest_sha256,
            ),
            "machine_id": (model.machine_id, report.machine.machine_id),
            "evidence_package_id": (
                model.evidence_package_id,
                report.evidence_reference.package_id,
            ),
            "evidence_package_digest_sha256": (
                model.evidence_package_digest_sha256,
                report.evidence_reference.package_digest_sha256,
            ),
            "retrieval_bundle_digest_sha256": (
                model.retrieval_bundle_digest_sha256,
                report.retrieval_reference.retrieval_bundle_digest_sha256,
            ),
            "generation_status": (
                model.generation_status,
                report.generation_status.value,
            ),
            "generated_at": (model.generated_at, report.generated_at),
            "schema_version": (model.schema_version, report.schema_version),
        },
    )
    return report


def _require_exact_replay(
    artifact_name: str,
    identity: object,
    existing: object,
    expected: Mapping[str, object],
) -> None:
    if any(getattr(existing, field) != value for field, value in expected.items()):
        raise ArtifactIdentityConflictError(
            f"{artifact_name} identity {identity} already exists with different content"
        )


def _require_stored_metadata(
    artifact_name: str,
    values: Mapping[str, tuple[object, object]],
) -> None:
    mismatches = [
        name for name, (stored, reconstructed) in values.items() if stored != reconstructed
    ]
    if mismatches:
        fields = ", ".join(mismatches)
        raise ArtifactPersistenceIntegrityError(
            f"Stored {artifact_name} relational metadata does not match payload: {fields}"
        )
