from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from domain.entities.analysis import Analysis
from domain.entities.machine import Machine
from modules.copilot.report import MaintenanceReport
from modules.retriever.models import RetrievalBundle
from shared.evidence.models import EvidencePackage


@dataclass(frozen=True)
class HistoricalMaintenanceWorkflow:
    machine: Machine
    analysis: Analysis
    evidence_package: EvidencePackage
    retrieval_bundle: RetrievalBundle
    maintenance_report: MaintenanceReport


class MaintenanceWorkflowRepository(Protocol):
    async def save_analysis(self, analysis: Analysis) -> None: ...

    async def save_evidence_package(self, package: EvidencePackage) -> None: ...

    async def save_retrieval_bundle(self, bundle: RetrievalBundle) -> None: ...

    async def save_maintenance_report(self, report: MaintenanceReport) -> None: ...

    async def get_by_report_id(
        self,
        report_id: UUID,
    ) -> HistoricalMaintenanceWorkflow | None: ...

    async def list_for_machine(
        self,
        machine_id: UUID,
    ) -> list[HistoricalMaintenanceWorkflow]: ...
