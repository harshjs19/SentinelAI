from collections.abc import Mapping
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ai_core.model_capabilities import get_runtime_default_capability
from ai_core.model_provenance import (
    ProducingModelContext,
    snapshot_producing_model_context,
)
from backend.app.config import get_settings
from backend.app.db.session import get_session
from backend.app.errors import model_unavailable_error
from backend.app.repositories.sqlalchemy_machine_repository import (
    SQLAlchemyMachineRepository,
)
from backend.app.repositories.sqlalchemy_maintenance_workflow_repository import (
    SQLAlchemyMaintenanceWorkflowRepository,
)
from backend.app.services.audio_inference_service import AudioInferenceService
from backend.app.services.decision_service import DecisionService
from backend.app.services.evidence_package_service import EvidencePackageService
from backend.app.services.machine_service import MachineService
from backend.app.services.maintenance_workflow_persistence_service import (
    MaintenanceWorkflowPersistenceService,
)
from backend.app.services.maintenance_workflow_service import MaintenanceWorkflowService
from backend.app.services.thermal_inference_service import ThermalInferenceService
from backend.app.services.timeseries_inference_service import TimeseriesInferenceService
from backend.app.services.vision_inference_service import VisionInferenceService
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.orchestrator import InferenceOrchestrator
from modules.audio.input import AudioInput
from modules.audio.predictor import AudioPredictor
from modules.copilot.service import MaintenanceCopilotService
from modules.copilot.validation import MaintenanceSafetyValidator
from modules.decision.engine import DecisionEngine
from modules.retriever.config import (
    CHROMA_PATH,
    COLLECTION_NAME,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_ID,
    EMBEDDING_MODEL_PATH,
    EMBEDDING_MODEL_REVISION,
    MANIFEST_PATH,
)
from modules.retriever.corpus import load_corpus
from modules.retriever.embedding import SentenceTransformerEmbedder
from modules.retriever.models import EmbeddingIdentity
from modules.retriever.retriever import KnowledgeRetriever
from modules.retriever.store import ChromaKnowledgeStore
from modules.thermal.input import ThermalInput
from modules.thermal.predictor import ThermalPredictor
from modules.timeseries.predictor import TimeseriesPredictor
from modules.vision.input import VisionInput
from modules.vision.predictor import VisionPredictor

SessionDependency = Annotated[AsyncSession, Depends(get_session, scope="function")]


def get_machine_service(session: SessionDependency) -> MachineService:
    return MachineService(SQLAlchemyMachineRepository(session))


def get_maintenance_workflow_persistence_service(
    session: SessionDependency,
) -> MaintenanceWorkflowPersistenceService:
    return MaintenanceWorkflowPersistenceService(SQLAlchemyMaintenanceWorkflowRepository(session))


@lru_cache
def get_event_bus() -> EventBus:
    return EventBus()


@lru_cache
def get_decision_engine() -> DecisionEngine:
    return DecisionEngine()


@lru_cache
def get_decision_service() -> DecisionService:
    return DecisionService(get_decision_engine(), get_event_bus())


@lru_cache
def get_timeseries_predictor() -> TimeseriesPredictor:
    artifact_path = get_settings().timeseries_model_path
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Time-series model artifact not found: {artifact_path}")
    return TimeseriesPredictor(artifact_path)


@lru_cache
def get_inference_orchestrator() -> InferenceOrchestrator:
    return InferenceOrchestrator(get_event_bus())


def _runtime_model_context(
    modality: Modality,
    model_id: str,
) -> ProducingModelContext:
    capability = get_runtime_default_capability(modality)
    if capability.model_id != model_id:
        raise RuntimeError(
            f"Configured {modality.value} predictor model does not match the runtime default"
        )
    return snapshot_producing_model_context(capability)


@lru_cache
def get_timeseries_inference_service() -> TimeseriesInferenceService:
    try:
        predictor = get_timeseries_predictor()
        orchestrator = get_inference_orchestrator()
        orchestrator.register(
            Modality.TIMESERIES,
            predictor,
            input_type=Mapping,
            producing_model=_runtime_model_context(Modality.TIMESERIES, predictor.model_id),
        )
        return TimeseriesInferenceService(orchestrator)
    except FileNotFoundError:
        raise model_unavailable_error("Time-series") from None


@lru_cache
def get_audio_predictor() -> AudioPredictor:
    settings = get_settings()
    artifact_path = settings.audio_model_path
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Audio model artifact not found: {artifact_path}")
    return AudioPredictor(
        artifact_path,
        encoder_path=settings.audio_encoder_path,
        device=settings.audio_encoder_device,
    )


@lru_cache
def get_audio_inference_service() -> AudioInferenceService:
    try:
        predictor = get_audio_predictor()
        orchestrator = get_inference_orchestrator()
        orchestrator.register(
            Modality.AUDIO,
            predictor,
            input_type=AudioInput,
            producing_model=_runtime_model_context(Modality.AUDIO, predictor.model_id),
        )
        return AudioInferenceService(orchestrator, predictor.supported_asset_types)
    except FileNotFoundError:
        raise model_unavailable_error("Audio") from None


@lru_cache
def get_vision_predictor() -> VisionPredictor:
    settings = get_settings()
    artifact_path = settings.vision_model_path
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Vision model artifact not found: {artifact_path}")
    return VisionPredictor(
        artifact_path,
        encoder_path=settings.vision_encoder_path,
        device=settings.vision_device,
    )


@lru_cache
def get_vision_inference_service() -> VisionInferenceService:
    try:
        predictor = get_vision_predictor()
        orchestrator = get_inference_orchestrator()
        orchestrator.register(
            Modality.VISION,
            predictor,
            input_type=VisionInput,
            producing_model=_runtime_model_context(Modality.VISION, predictor.model_id),
        )
        return VisionInferenceService(orchestrator, predictor.supported_asset_types)
    except FileNotFoundError:
        raise model_unavailable_error("Vision") from None


@lru_cache
def get_thermal_predictor() -> ThermalPredictor:
    settings = get_settings()
    artifact_path = settings.thermal_model_path
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Thermal model artifact not found: {artifact_path}")
    return ThermalPredictor(
        artifact_path,
        encoder_path=settings.thermal_encoder_path,
        device=settings.thermal_device,
    )


@lru_cache
def get_thermal_inference_service() -> ThermalInferenceService:
    try:
        predictor = get_thermal_predictor()
        orchestrator = get_inference_orchestrator()
        orchestrator.register(
            Modality.THERMAL,
            predictor,
            input_type=ThermalInput,
            producing_model=_runtime_model_context(Modality.THERMAL, predictor.model_id),
        )
        return ThermalInferenceService(orchestrator, predictor.supported_asset_types)
    except FileNotFoundError:
        raise model_unavailable_error("Thermal") from None


@lru_cache
def get_evidence_package_service() -> EvidencePackageService:
    return EvidencePackageService()


@lru_cache
def get_knowledge_retriever() -> KnowledgeRetriever:
    identity = EmbeddingIdentity(
        model_id=EMBEDDING_MODEL_ID,
        revision=EMBEDDING_MODEL_REVISION,
        dimension=EMBEDDING_DIMENSION,
    )
    corpus = load_corpus(MANIFEST_PATH, identity)
    return KnowledgeRetriever(
        store=ChromaKnowledgeStore(CHROMA_PATH, COLLECTION_NAME),
        embedder=SentenceTransformerEmbedder(EMBEDDING_MODEL_PATH, identity),
        corpus_digest_sha256=corpus.corpus_digest_sha256,
    )


@lru_cache
def get_maintenance_copilot_service() -> MaintenanceCopilotService:
    return MaintenanceCopilotService(
        generator=None,
        validator=MaintenanceSafetyValidator(),
    )


def get_maintenance_workflow_service(
    session: SessionDependency,
) -> MaintenanceWorkflowService:
    return MaintenanceWorkflowService(
        machine_service=get_machine_service(session),
        timeseries_inference_factory=get_timeseries_inference_service,
        audio_inference_factory=get_audio_inference_service,
        vision_inference_factory=get_vision_inference_service,
        thermal_inference_factory=get_thermal_inference_service,
        decision_service=get_decision_service(),
        evidence_package_service=get_evidence_package_service(),
        knowledge_retriever_factory=get_knowledge_retriever,
        copilot_service=get_maintenance_copilot_service(),
    )
