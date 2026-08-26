from dataclasses import dataclass
from uuid import UUID

from backend.app.persistence.errors import ArtifactPersistenceIntegrityError
from backend.app.persistence.maintenance_artifact_mapper import validate_artifact_chain
from backend.app.repositories.maintenance_workflow_repository import (
    HistoricalMaintenanceWorkflow,
    MaintenanceWorkflowRepository,
)
from backend.app.services.maintenance_workflow_service import MaintenanceWorkflowResult
from shared.evidence.models import snapshot_model


@dataclass(frozen=True)
class PersistedMaintenanceWorkflowReference:
    analysis_id: UUID
    evidence_package_id: str
    evidence_package_digest_sha256: str
    retrieval_bundle_digest_sha256: str
    maintenance_report_id: UUID
    maintenance_report_digest_sha256: str


class MaintenanceWorkflowPersistenceService:
    """Persist only complete, already-produced maintenance workflow results."""

    def __init__(self, repository: MaintenanceWorkflowRepository) -> None:
        self._repository = repository

    async def persist(
        self,
        result: MaintenanceWorkflowResult,
    ) -> PersistedMaintenanceWorkflowReference:
        self._validate_workflow_result(result)
        await self._repository.save_analysis(result.analysis)
        await self._repository.save_evidence_package(result.evidence_package)
        await self._repository.save_retrieval_bundle(result.retrieval_bundle)
        await self._repository.save_maintenance_report(result.maintenance_report)
        return PersistedMaintenanceWorkflowReference(
            analysis_id=result.analysis.id,
            evidence_package_id=result.evidence_package.package_id,
            evidence_package_digest_sha256=result.evidence_package.package_digest_sha256,
            retrieval_bundle_digest_sha256=(result.retrieval_bundle.retrieval_bundle_digest_sha256),
            maintenance_report_id=result.maintenance_report.report_id,
            maintenance_report_digest_sha256=result.maintenance_report.report_digest_sha256,
        )

    async def get_by_report_id(
        self,
        report_id: UUID,
    ) -> HistoricalMaintenanceWorkflow | None:
        return await self._repository.get_by_report_id(report_id)

    async def list_for_machine(
        self,
        machine_id: UUID,
    ) -> list[HistoricalMaintenanceWorkflow]:
        return await self._repository.list_for_machine(machine_id)

    @staticmethod
    def _validate_workflow_result(result: MaintenanceWorkflowResult) -> None:
        validate_artifact_chain(
            result.analysis,
            result.evidence_package,
            result.retrieval_bundle,
            result.maintenance_report,
        )
        if result.analysis.predictions != (result.inference_result.prediction,):
            raise ArtifactPersistenceIntegrityError(
                "Workflow Analysis does not contain the exact inference Prediction"
            )
        if result.evidence_package.models != (
            snapshot_model(result.inference_result.producing_model),
        ):
            raise ArtifactPersistenceIntegrityError(
                "Evidence Package does not retain the exact producing-model provenance"
            )
