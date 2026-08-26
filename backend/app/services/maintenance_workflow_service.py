from collections.abc import Callable, Mapping
from dataclasses import dataclass
from uuid import UUID

from backend.app.services.audio_inference_service import AudioInferenceService
from backend.app.services.decision_service import DecisionService
from backend.app.services.evidence_package_service import EvidencePackageService
from backend.app.services.machine_service import MachineService
from backend.app.services.thermal_inference_service import ThermalInferenceService
from backend.app.services.timeseries_inference_service import TimeseriesInferenceService
from backend.app.services.vision_inference_service import VisionInferenceService
from domain.entities.analysis import Analysis
from domain.enums.modality import Modality
from inference.result import InferenceResult
from modules.copilot.contracts import (
    CopilotIntent,
    MaintenanceCopilotRequest,
    normalize_question,
)
from modules.copilot.report import MaintenanceReport, verify_report_digest
from modules.copilot.service import MaintenanceCopilotService
from modules.retriever.models import RetrievalBundle, verify_retrieval_bundle_digest
from modules.retriever.retriever import KnowledgeRetriever
from shared.evidence.models import EvidencePackage, verify_evidence_package_digest
from shared.evidence.provenance import (
    SourceProvenance,
    file_source_provenance,
    structured_source_provenance,
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8"


class MaintenanceWorkflowMachineNotFoundError(LookupError):
    pass


class MaintenanceWorkflowIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class TimeseriesMaintenanceRequest:
    machine_id: UUID
    samples: tuple[Mapping[str, float], ...]
    intent: CopilotIntent
    question: str | None = None


@dataclass(frozen=True, kw_only=True)
class AudioMaintenanceRequest:
    machine_id: UUID
    content: bytes
    intent: CopilotIntent
    question: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise TypeError("Audio maintenance content must be exact bytes")


@dataclass(frozen=True, kw_only=True)
class VisionMaintenanceRequest:
    machine_id: UUID
    content: bytes
    intent: CopilotIntent
    question: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise TypeError("Vision maintenance content must be exact bytes")


@dataclass(frozen=True, kw_only=True)
class ThermalMaintenanceRequest:
    machine_id: UUID
    content: bytes
    intent: CopilotIntent
    question: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise TypeError("Thermal maintenance content must be exact bytes")


type MaintenanceWorkflowRequest = (
    TimeseriesMaintenanceRequest
    | AudioMaintenanceRequest
    | VisionMaintenanceRequest
    | ThermalMaintenanceRequest
)


@dataclass(frozen=True)
class MaintenanceWorkflowResult:
    inference_result: InferenceResult
    analysis: Analysis
    evidence_package: EvidencePackage
    retrieval_bundle: RetrievalBundle
    maintenance_report: MaintenanceReport


class MaintenanceWorkflowService:
    """Compose one server-owned, single-modality maintenance workflow."""

    def __init__(
        self,
        *,
        machine_service: MachineService,
        timeseries_inference_factory: Callable[[], TimeseriesInferenceService],
        audio_inference_factory: Callable[[], AudioInferenceService],
        vision_inference_factory: Callable[[], VisionInferenceService],
        thermal_inference_factory: Callable[[], ThermalInferenceService],
        decision_service: DecisionService,
        evidence_package_service: EvidencePackageService,
        knowledge_retriever_factory: Callable[[], KnowledgeRetriever],
        copilot_service: MaintenanceCopilotService,
    ) -> None:
        self._machine_service = machine_service
        self._timeseries_inference_factory = timeseries_inference_factory
        self._audio_inference_factory = audio_inference_factory
        self._vision_inference_factory = vision_inference_factory
        self._thermal_inference_factory = thermal_inference_factory
        self._decision_service = decision_service
        self._evidence_package_service = evidence_package_service
        self._knowledge_retriever_factory = knowledge_retriever_factory
        self._copilot_service = copilot_service

    async def execute(
        self,
        request: MaintenanceWorkflowRequest,
    ) -> MaintenanceWorkflowResult:
        question = normalize_question(request.question)
        machine = await self._machine_service.get_machine(request.machine_id)
        if machine is None:
            raise MaintenanceWorkflowMachineNotFoundError(
                f"Machine not found: {request.machine_id}"
            )

        inference_result, source = await self._infer(machine.asset_type, request)
        analysis = await self._decision_service.analyze(
            machine.id,
            (inference_result.prediction,),
        )
        if analysis.predictions != (inference_result.prediction,):
            raise MaintenanceWorkflowIntegrityError(
                "DecisionService returned Analysis for different prediction evidence"
            )

        evidence_package = self._evidence_package_service.build(
            machine,
            analysis,
            (source,),
            producing_models=(inference_result.producing_model,),
        )
        if not verify_evidence_package_digest(evidence_package):
            raise MaintenanceWorkflowIntegrityError(
                "Evidence Package integrity verification failed"
            )

        retrieval_bundle = self._knowledge_retriever_factory().retrieve(evidence_package)
        self._verify_retrieval_binding(evidence_package, retrieval_bundle)

        maintenance_report = await self._copilot_service.generate_report(
            MaintenanceCopilotRequest(
                evidence_package=evidence_package,
                retrieval_bundle=retrieval_bundle,
                intent=request.intent,
                question=question,
            )
        )
        self._verify_report_binding(evidence_package, retrieval_bundle, maintenance_report)
        return MaintenanceWorkflowResult(
            inference_result=inference_result,
            analysis=analysis,
            evidence_package=evidence_package,
            retrieval_bundle=retrieval_bundle,
            maintenance_report=maintenance_report,
        )

    async def _infer(
        self,
        asset_type: str,
        request: MaintenanceWorkflowRequest,
    ) -> tuple[InferenceResult, SourceProvenance]:
        if isinstance(request, TimeseriesMaintenanceRequest):
            samples = tuple(dict(sample) for sample in request.samples)
            result = await self._timeseries_inference_factory().predict(
                request.machine_id,
                samples,
            )
            source = structured_source_provenance(
                Modality.TIMESERIES,
                {"samples": samples},
            )
            return result, source

        if isinstance(request, AudioMaintenanceRequest):
            service = self._audio_inference_factory()
            service.validate_asset_type(asset_type)
            result = await service.predict(request.machine_id, request.content)
            source = file_source_provenance(
                Modality.AUDIO,
                request.content,
                "audio/wav",
            )
            return result, source

        if isinstance(request, VisionMaintenanceRequest):
            service = self._vision_inference_factory()
            service.validate_asset_type(asset_type)
            result = await service.predict(request.machine_id, request.content)
            source = file_source_provenance(
                Modality.VISION,
                request.content,
                _image_content_type(request.content),
            )
            return result, source

        if isinstance(request, ThermalMaintenanceRequest):
            service = self._thermal_inference_factory()
            service.validate_asset_type(asset_type)
            result = await service.predict(request.machine_id, request.content)
            source = file_source_provenance(
                Modality.THERMAL,
                request.content,
                _image_content_type(request.content),
            )
            return result, source

        raise TypeError("Unsupported maintenance workflow request type")

    @staticmethod
    def _verify_retrieval_binding(
        package: EvidencePackage,
        bundle: RetrievalBundle,
    ) -> None:
        if not verify_retrieval_bundle_digest(bundle):
            raise MaintenanceWorkflowIntegrityError(
                "Retrieval Bundle integrity verification failed"
            )
        if (
            bundle.evidence_package_id != package.package_id
            or bundle.evidence_package_digest_sha256 != package.package_digest_sha256
        ):
            raise MaintenanceWorkflowIntegrityError(
                "Retrieval Bundle does not belong to the workflow Evidence Package"
            )

    @staticmethod
    def _verify_report_binding(
        package: EvidencePackage,
        bundle: RetrievalBundle,
        report: MaintenanceReport,
    ) -> None:
        if not verify_report_digest(report):
            raise MaintenanceWorkflowIntegrityError(
                "Maintenance Report integrity verification failed"
            )
        if (
            report.evidence_reference.package_id != package.package_id
            or report.evidence_reference.package_digest_sha256 != package.package_digest_sha256
            or report.retrieval_reference.evidence_package_id != bundle.evidence_package_id
            or report.retrieval_reference.retrieval_bundle_digest_sha256
            != bundle.retrieval_bundle_digest_sha256
            or report.producing_models != package.models
        ):
            raise MaintenanceWorkflowIntegrityError(
                "Maintenance Report does not belong to the workflow evidence chain"
            )


def _image_content_type(content: bytes) -> str:
    if content.startswith(_PNG_SIGNATURE):
        return "image/png"
    if content.startswith(_JPEG_SIGNATURE):
        return "image/jpeg"
    raise MaintenanceWorkflowIntegrityError(
        "Successful image inference did not receive JPEG or PNG source bytes"
    )
