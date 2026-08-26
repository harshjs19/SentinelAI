import hashlib
import io
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from uuid import UUID

import pytest
from PIL import Image

import ai_core.model_capabilities as model_capabilities
import backend.app.dependencies as dependencies
from ai_core.model_capabilities import ModelCapability, ModelLifecycleStatus
from ai_core.model_provenance import ProducingModelContext, snapshot_producing_model_context
from backend.app.services.decision_service import DecisionService
from backend.app.services.evidence_package_service import EvidencePackageService
from backend.app.services.maintenance_workflow_service import (
    AudioMaintenanceRequest,
    MaintenanceWorkflowIntegrityError,
    MaintenanceWorkflowMachineNotFoundError,
    MaintenanceWorkflowRequest,
    MaintenanceWorkflowResult,
    MaintenanceWorkflowService,
    ThermalMaintenanceRequest,
    TimeseriesMaintenanceRequest,
    VisionMaintenanceRequest,
)
from backend.app.services.vision_inference_service import (
    UnsupportedVisionAssetTypeError,
    VisionInferenceService,
)
from domain.entities.analysis import Analysis
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.condition_state import ConditionState
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import AnalysisProduced, PredictionProduced
from inference.orchestrator import InferenceOrchestrator
from inference.result import InferenceResult
from modules.copilot.context import CopilotContextBuilder, generation_context_payload
from modules.copilot.contracts import (
    CopilotDraft,
    CopilotIntent,
    FallbackReason,
    GenerationStatus,
    MaintenanceCopilotRequest,
    SafetyViolationCode,
)
from modules.copilot.report import verify_maintenance_report, verify_report_digest
from modules.copilot.service import MaintenanceCopilotService
from modules.copilot.validation import MaintenanceSafetyValidator
from modules.decision.engine import DecisionEngine
from modules.retriever.exceptions import RetrievalUnavailableError
from modules.retriever.models import (
    EmbeddingIdentity,
    RetrievalBundle,
    create_retrieval_bundle,
    verify_retrieval_bundle_digest,
)
from modules.vision.input import VisionInput
from shared.evidence.canonical import canonical_json_bytes
from shared.evidence.models import EvidencePackage
from shared.evidence.provenance import SourceKind
from tests.copilot.support import (
    ChunkSpec,
    FakeMaintenanceGenerator,
    generated_result,
    make_bundle,
    make_valid_draft,
)

_MACHINE_ID = UUID("00000000-0000-0000-0000-000000007001")


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color=(32, 64, 96)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeMachineService:
    def __init__(self, machine: Machine | None) -> None:
        self.machine = machine
        self.calls = 0

    async def get_machine(self, machine_id: UUID) -> Machine | None:
        self.calls += 1
        if self.machine is not None and self.machine.id == machine_id:
            return self.machine
        return None


class RecordingInferenceService:
    def __init__(
        self,
        modality: Modality,
        label: str,
        *,
        on_predict: Callable[[], None] | None = None,
        producing_model: ProducingModelContext | None = None,
    ) -> None:
        self.modality = modality
        self.label = label
        self.on_predict = on_predict
        self.producing_model = producing_model or _model_context(modality)
        self.asset_types: list[str] = []
        self.inputs: list[object] = []

    def validate_asset_type(self, asset_type: str) -> None:
        self.asset_types.append(asset_type)

    async def predict(self, machine_id: UUID, input_data: object) -> InferenceResult:
        self.inputs.append(input_data)
        if self.on_predict is not None:
            self.on_predict()
        return InferenceResult(
            prediction=Prediction(self.modality, self.label, 0.91),
            producing_model=self.producing_model,
        )


class RecordingRetriever:
    def __init__(self) -> None:
        self.packages: list[EvidencePackage] = []

    def retrieve(self, package: EvidencePackage) -> RetrievalBundle:
        self.packages.append(package)
        finding = package.analysis.findings[0]
        return make_bundle(
            package,
            (
                ChunkSpec(
                    finding.code,
                    asset_type=package.machine.asset_type,
                    text="Synthetic source-backed inspection context.",
                ),
            ),
        )


class FailingRetriever(RecordingRetriever):
    def retrieve(self, package: EvidencePackage) -> RetrievalBundle:
        self.packages.append(package)
        raise RetrievalUnavailableError("Synthetic retrieval failure")


class MismatchedRetriever(RecordingRetriever):
    def retrieve(self, package: EvidencePackage) -> RetrievalBundle:
        bundle = super().retrieve(package)
        return create_retrieval_bundle(
            evidence_package_id=f"evp1_{'f' * 32}",
            evidence_package_digest_sha256="f" * 64,
            corpus_digest_sha256=bundle.corpus_digest_sha256,
            embedding_identity=EmbeddingIdentity(
                bundle.embedding_model_id,
                bundle.embedding_model_revision,
                8,
            ),
            collection_name=bundle.collection_name,
            queries=bundle.queries,
            chunks=bundle.chunks,
        )


class TamperingEvidencePackageService(EvidencePackageService):
    def build(self, *args: object, **kwargs: object) -> EvidencePackage:
        package = super().build(*args, **kwargs)  # type: ignore[arg-type]
        object.__setattr__(package, "package_digest_sha256", "0" * 64)
        return package


class RecordingVisionPredictor:
    def __init__(self) -> None:
        self.inputs: list[VisionInput] = []

    def predict(self, input_data: VisionInput) -> Prediction:
        self.inputs.append(input_data)
        return Prediction(Modality.VISION, "visual_anomaly", 0.91)


class FailingDecisionService:
    async def analyze(
        self,
        machine_id: UUID,
        predictions: tuple[Prediction, ...],
    ) -> Analysis:
        raise RuntimeError("Synthetic DecisionService failure")


class MismatchedDecisionService:
    async def analyze(
        self,
        machine_id: UUID,
        predictions: tuple[Prediction, ...],
    ) -> Analysis:
        return DecisionEngine().evaluate(
            machine_id,
            (Prediction(Modality.VISION, "healthy", 0.99),),
        )


@dataclass
class Factory:
    service: object | None = None
    error: Exception | None = None
    calls: int = 0

    def __call__(self) -> object:
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.service is None:
            raise AssertionError("Unexpected inference service resolution")
        return self.service


def test_composition_root_keeps_inference_and_retrieval_resolution_lazy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolutions: list[str] = []

    def unexpected_resolution(name: str) -> Callable[[], object]:
        def resolve() -> object:
            resolutions.append(name)
            raise AssertionError(f"Unexpected eager resolution: {name}")

        return resolve

    bus = EventBus()
    monkeypatch.setattr(
        dependencies,
        "get_machine_service",
        lambda session: FakeMachineService(None),
    )
    monkeypatch.setattr(
        dependencies,
        "get_timeseries_inference_service",
        unexpected_resolution("timeseries"),
    )
    monkeypatch.setattr(
        dependencies,
        "get_audio_inference_service",
        unexpected_resolution("audio"),
    )
    monkeypatch.setattr(
        dependencies,
        "get_vision_inference_service",
        unexpected_resolution("vision"),
    )
    monkeypatch.setattr(
        dependencies,
        "get_thermal_inference_service",
        unexpected_resolution("thermal"),
    )
    monkeypatch.setattr(
        dependencies,
        "get_knowledge_retriever",
        unexpected_resolution("retriever"),
    )
    monkeypatch.setattr(
        dependencies,
        "get_decision_service",
        lambda: DecisionService(DecisionEngine(), bus),
    )
    monkeypatch.setattr(
        dependencies,
        "get_evidence_package_service",
        EvidencePackageService,
    )
    monkeypatch.setattr(
        dependencies,
        "get_maintenance_copilot_service",
        lambda: MaintenanceCopilotService(
            generator=None,
            validator=MaintenanceSafetyValidator(),
        ),
    )

    service = dependencies.get_maintenance_workflow_service(object())  # type: ignore[arg-type]

    assert isinstance(service, MaintenanceWorkflowService)
    assert resolutions == []


@pytest.mark.parametrize(
    ("workflow_request", "machine", "modality", "label", "expected_content_type"),
    [
        pytest.param(
            TimeseriesMaintenanceRequest(
                machine_id=_MACHINE_ID,
                samples=({"ch1": 1.0}, {"ch1": 2.0}),
                intent=CopilotIntent.EXPLAIN_CONFIDENCE,
            ),
            Machine(_MACHINE_ID, "Time-Series fixture", "pump"),
            Modality.TIMESERIES,
            "bearing_fault",
            "application/json",
            id="timeseries",
        ),
        pytest.param(
            AudioMaintenanceRequest(
                machine_id=_MACHINE_ID,
                content=b"RIFF synthetic exact WAV bytes",
                intent=CopilotIntent.EXPLAIN_CONFIDENCE,
            ),
            Machine(_MACHINE_ID, "Audio fixture", "bearing"),
            Modality.AUDIO,
            "acoustic_anomaly",
            "audio/wav",
            id="audio",
        ),
        pytest.param(
            VisionMaintenanceRequest(
                machine_id=_MACHINE_ID,
                content=_png_bytes(),
                intent=CopilotIntent.EXPLAIN_CONFIDENCE,
            ),
            Machine(_MACHINE_ID, "Vision fixture", "pcb1"),
            Modality.VISION,
            "visual_anomaly",
            "image/png",
            id="vision",
        ),
        pytest.param(
            ThermalMaintenanceRequest(
                machine_id=_MACHINE_ID,
                content=_png_bytes(),
                intent=CopilotIntent.EXPLAIN_CONFIDENCE,
            ),
            Machine(
                _MACHINE_ID,
                "Thermal fixture",
                "rotating_electromechanical_system",
            ),
            Modality.THERMAL,
            "gear_wear_75",
            "image/png",
            id="thermal",
        ),
    ],
)
@pytest.mark.asyncio
async def test_all_modalities_derive_provenance_from_exact_inference_input(
    workflow_request: MaintenanceWorkflowRequest,
    machine: Machine,
    modality: Modality,
    label: str,
    expected_content_type: str,
) -> None:
    inference = RecordingInferenceService(modality, label)
    generator = FakeMaintenanceGenerator()
    retriever = RecordingRetriever()
    service = _workflow_service(
        machine=machine,
        inference_services={modality: inference},
        retriever=retriever,
        generator=generator,
    )

    result = await service.execute(workflow_request)

    assert len(inference.inputs) == 1
    source = result.evidence_package.sources[0]
    assert source.modality is modality
    assert source.content_type == expected_content_type
    if isinstance(workflow_request, TimeseriesMaintenanceRequest):
        expected_payload = {"samples": tuple(dict(sample) for sample in workflow_request.samples)}
        expected_bytes = canonical_json_bytes(expected_payload)
        assert source.source_kind is SourceKind.STRUCTURED
        assert source.size_bytes == len(expected_bytes)
        assert source.sha256 == hashlib.sha256(expected_bytes).hexdigest()
        assert inference.inputs == [tuple(dict(sample) for sample in workflow_request.samples)]
    else:
        assert source.source_kind is SourceKind.FILE
        assert source.size_bytes == len(workflow_request.content)
        assert source.sha256 == hashlib.sha256(workflow_request.content).hexdigest()
        assert inference.inputs == [workflow_request.content]
        assert inference.asset_types == [machine.asset_type]
    assert result.evidence_package.models[0].model_id == _model_context(modality).model_id
    assert not hasattr(result, "content")
    assert not hasattr(result, "samples")
    assert generator.calls == []


@pytest.mark.asyncio
async def test_deterministic_workflow_preserves_evidence_and_emits_existing_events_once() -> None:
    machine = Machine(_MACHINE_ID, "PCB inspection fixture", "pcb1")
    event_bus = EventBus()
    predictor = RecordingVisionPredictor()
    vision_service = _vision_service(event_bus, predictor)
    events: list[object] = []

    async def record_prediction(event: PredictionProduced) -> None:
        events.append(event)

    async def record_analysis(event: AnalysisProduced) -> None:
        events.append(event)

    event_bus.subscribe(PredictionProduced, record_prediction)
    event_bus.subscribe(AnalysisProduced, record_analysis)
    generator = FakeMaintenanceGenerator()
    retriever = RecordingRetriever()
    service = _workflow_service(
        machine=machine,
        inference_services={Modality.VISION: vision_service},
        retriever=retriever,
        generator=generator,
        event_bus=event_bus,
    )

    result = await service.execute(
        VisionMaintenanceRequest(
            machine_id=machine.id,
            content=_png_bytes(),
            intent=CopilotIntent.EXPLAIN_CONFIDENCE,
        )
    )

    assert [type(event) for event in events] == [PredictionProduced, AnalysisProduced]
    assert result.analysis.condition is ConditionState.ABNORMAL
    assert result.analysis.findings == result.evidence_package.analysis.findings
    assert AnalysisLimitation.SINGLE_MODALITY_EVIDENCE in result.analysis.limitations
    assert (
        AnalysisLimitation.SINGLE_MODALITY_EVIDENCE
        in result.maintenance_report.limitations.analysis_limitations
    )
    assert result.evidence_package.models == result.maintenance_report.producing_models
    assert result.evidence_package.models[0].model_id == "vision_visa_pcb1_v1"
    assert result.maintenance_report.generation_status is GenerationStatus.DETERMINISTIC
    assert verify_retrieval_bundle_digest(result.retrieval_bundle)
    _assert_report_verifies(result, CopilotIntent.EXPLAIN_CONFIDENCE)
    assert generator.calls == []


@pytest.mark.asyncio
async def test_generated_workflow_passes_only_bounded_context_and_verifies_report() -> None:
    generator = FakeMaintenanceGenerator(
        generated_result(
            make_valid_draft(
                summary="The analysis reported a visual anomaly.",
                finding_text="The cited source provides visual-anomaly inspection context.",
            )
        )
    )
    service, request = _vision_workflow(generator=generator)

    result = await service.execute(request)

    assert result.maintenance_report.generation_status is GenerationStatus.GENERATED
    assert len(generator.calls) == 1
    context, repair = generator.calls[0]
    assert repair is None
    payload = generation_context_payload(context)
    assert "machine_id" not in payload
    assert "machine_name" not in payload
    assert "model_id" not in str(payload)
    assert "source" not in payload
    assert "sha256" not in str(payload)
    assert result.maintenance_report.citations[0].citation_id == "K1"
    assert result.maintenance_report.producing_models[0].model_id == "vision_visa_pcb1_v1"
    _assert_report_verifies(result, request.intent)


@pytest.mark.asyncio
async def test_unsafe_generated_draft_uses_existing_repair_then_safe_fallback() -> None:
    unsafe = CopilotDraft(executive_summary="Shut down the machine immediately.")
    generator = FakeMaintenanceGenerator(
        generated_result(unsafe),
        generated_result(unsafe, repair_attempted=True),
    )
    service, request = _vision_workflow(generator=generator)

    result = await service.execute(request)

    report = result.maintenance_report
    assert len(generator.calls) == 2
    assert report.generation_status is GenerationStatus.FALLBACK
    assert report.fallback_reason is FallbackReason.VALIDATION_FAILED
    assert "shut down" not in report.narrative.executive_summary.lower()
    assert SafetyViolationCode.HIGH_IMPACT_ACTION in {
        violation.code for violation in report.safety_validation.violations
    }
    _assert_report_verifies(result, request.intent)


@pytest.mark.asyncio
async def test_high_impact_question_bypasses_generator() -> None:
    generator = FakeMaintenanceGenerator()
    service, request = _vision_workflow(
        generator=generator,
        question="Should I shut this machine down now?",
    )

    result = await service.execute(request)

    assert generator.calls == []
    assert result.maintenance_report.generation_status is GenerationStatus.FALLBACK
    assert result.maintenance_report.fallback_reason is FallbackReason.UNSUPPORTED_REQUEST
    _assert_report_verifies(result, request.intent, question=request.question)


@pytest.mark.asyncio
async def test_provider_unavailable_returns_existing_safe_fallback() -> None:
    service, request = _vision_workflow(generator=None)

    result = await service.execute(request)

    assert result.maintenance_report.generation_status is GenerationStatus.FALLBACK
    assert result.maintenance_report.fallback_reason is FallbackReason.GENERATION_UNAVAILABLE
    _assert_report_verifies(result, request.intent)


@pytest.mark.asyncio
async def test_unknown_machine_stops_before_inference_retrieval_or_generation() -> None:
    factory = Factory(service=RecordingInferenceService(Modality.VISION, "visual_anomaly"))
    retriever = RecordingRetriever()
    generator = FakeMaintenanceGenerator()
    service = _workflow_service(
        machine=None,
        factories={Modality.VISION: factory},
        retriever=retriever,
        generator=generator,
    )

    with pytest.raises(MaintenanceWorkflowMachineNotFoundError):
        await service.execute(
            VisionMaintenanceRequest(
                machine_id=_MACHINE_ID,
                content=_png_bytes(),
                intent=CopilotIntent.EXPLAIN_FINDING,
            )
        )

    assert factory.calls == 0
    assert retriever.packages == []
    assert generator.calls == []


@pytest.mark.asyncio
async def test_unsupported_asset_stops_before_prediction_retrieval_or_generation() -> None:
    machine = Machine(_MACHINE_ID, "Unsupported fixture", "pump")
    event_bus = EventBus()
    predictor = RecordingVisionPredictor()
    generator = FakeMaintenanceGenerator()
    retriever = RecordingRetriever()
    service = _workflow_service(
        machine=machine,
        inference_services={Modality.VISION: _vision_service(event_bus, predictor)},
        retriever=retriever,
        generator=generator,
        event_bus=event_bus,
    )

    with pytest.raises(UnsupportedVisionAssetTypeError):
        await service.execute(
            VisionMaintenanceRequest(
                machine_id=machine.id,
                content=_png_bytes(),
                intent=CopilotIntent.EXPLAIN_FINDING,
            )
        )

    assert predictor.inputs == []
    assert retriever.packages == []
    assert generator.calls == []


@pytest.mark.asyncio
async def test_malformed_source_stops_before_prediction_retrieval_or_generation() -> None:
    machine = Machine(_MACHINE_ID, "PCB fixture", "pcb1")
    event_bus = EventBus()
    predictor = RecordingVisionPredictor()
    generator = FakeMaintenanceGenerator()
    retriever = RecordingRetriever()
    service = _workflow_service(
        machine=machine,
        inference_services={Modality.VISION: _vision_service(event_bus, predictor)},
        retriever=retriever,
        generator=generator,
        event_bus=event_bus,
    )

    with pytest.raises(ValueError, match="valid JPEG or PNG"):
        await service.execute(
            VisionMaintenanceRequest(
                machine_id=machine.id,
                content=b"not an image",
                intent=CopilotIntent.EXPLAIN_FINDING,
            )
        )

    assert predictor.inputs == []
    assert retriever.packages == []
    assert generator.calls == []


@pytest.mark.asyncio
async def test_missing_model_error_propagates_without_downstream_work() -> None:
    machine = Machine(_MACHINE_ID, "PCB fixture", "pcb1")
    factory = Factory(error=FileNotFoundError("synthetic missing model"))
    retriever = RecordingRetriever()
    generator = FakeMaintenanceGenerator()
    service = _workflow_service(
        machine=machine,
        factories={Modality.VISION: factory},
        retriever=retriever,
        generator=generator,
    )

    with pytest.raises(FileNotFoundError, match="synthetic missing model"):
        await service.execute(
            VisionMaintenanceRequest(
                machine_id=machine.id,
                content=_png_bytes(),
                intent=CopilotIntent.EXPLAIN_FINDING,
            )
        )

    assert factory.calls == 1
    assert retriever.packages == []
    assert generator.calls == []


@pytest.mark.asyncio
async def test_retrieval_failure_propagates_without_generation() -> None:
    generator = FakeMaintenanceGenerator()
    service, request = _vision_workflow(
        generator=generator,
        retriever=FailingRetriever(),
    )

    with pytest.raises(RetrievalUnavailableError):
        await service.execute(request)

    assert generator.calls == []


@pytest.mark.asyncio
async def test_decision_failure_propagates_without_downstream_work() -> None:
    retriever = RecordingRetriever()
    generator = FakeMaintenanceGenerator()
    service, request = _vision_workflow(
        generator=generator,
        retriever=retriever,
        decision_service=FailingDecisionService(),
    )

    with pytest.raises(RuntimeError, match="DecisionService failure"):
        await service.execute(request)

    assert retriever.packages == []
    assert generator.calls == []


@pytest.mark.asyncio
async def test_impossible_decision_output_is_rejected_before_evidence_retrieval() -> None:
    retriever = RecordingRetriever()
    generator = FakeMaintenanceGenerator()
    service, request = _vision_workflow(
        generator=generator,
        retriever=retriever,
        decision_service=MismatchedDecisionService(),
    )

    with pytest.raises(MaintenanceWorkflowIntegrityError, match="different prediction"):
        await service.execute(request)

    assert retriever.packages == []
    assert generator.calls == []


@pytest.mark.asyncio
async def test_tampered_evidence_is_rejected_before_retrieval_or_generation() -> None:
    retriever = RecordingRetriever()
    generator = FakeMaintenanceGenerator()
    service, request = _vision_workflow(
        generator=generator,
        retriever=retriever,
        evidence_service=TamperingEvidencePackageService(),
    )

    with pytest.raises(MaintenanceWorkflowIntegrityError, match="Evidence Package"):
        await service.execute(request)

    assert retriever.packages == []
    assert generator.calls == []


@pytest.mark.asyncio
async def test_mismatched_retrieval_bundle_is_rejected_before_generation() -> None:
    retriever = MismatchedRetriever()
    generator = FakeMaintenanceGenerator()
    service, request = _vision_workflow(generator=generator, retriever=retriever)

    with pytest.raises(MaintenanceWorkflowIntegrityError, match="does not belong"):
        await service.execute(request)

    assert len(retriever.packages) == 1
    assert generator.calls == []


@pytest.mark.asyncio
async def test_default_change_after_inference_does_not_change_evidence_or_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_default = ModelCapability(
        model_id="vision_fake_v2",
        modality=Modality.VISION,
        status=ModelLifecycleStatus.EXPERIMENTAL,
        runtime_default=True,
        validated_scope="Synthetic default-change regression only",
        evaluation_reference="evaluation/vision_baseline_results.json",
        confidence_semantics="bounded_empirical_visual_anomaly_evidence_from_normal_calibration",
    )

    def change_default() -> None:
        monkeypatch.setattr(
            model_capabilities,
            "get_runtime_default_capability",
            lambda modality: fake_default,
        )

    inference = RecordingInferenceService(
        Modality.VISION,
        "visual_anomaly",
        on_predict=change_default,
    )
    generator = FakeMaintenanceGenerator()
    machine = Machine(_MACHINE_ID, "PCB fixture", "pcb1")
    service = _workflow_service(
        machine=machine,
        inference_services={Modality.VISION: inference},
        generator=generator,
    )
    request = VisionMaintenanceRequest(
        machine_id=machine.id,
        content=_png_bytes(),
        intent=CopilotIntent.EXPLAIN_CONFIDENCE,
    )

    result = await service.execute(request)

    assert model_capabilities.get_runtime_default_capability(Modality.VISION) == fake_default
    assert result.inference_result.producing_model.model_id == "vision_visa_pcb1_v1"
    assert result.evidence_package.models[0].model_id == "vision_visa_pcb1_v1"
    assert result.maintenance_report.producing_models[0].model_id == "vision_visa_pcb1_v1"
    assert "vision_fake_v2" not in repr(result)
    assert generator.calls == []


def _workflow_service(
    *,
    machine: Machine | None,
    inference_services: Mapping[Modality, object] | None = None,
    factories: Mapping[Modality, Factory] | None = None,
    retriever: RecordingRetriever | None = None,
    generator: FakeMaintenanceGenerator | None = None,
    event_bus: EventBus | None = None,
    evidence_service: EvidencePackageService | None = None,
    decision_service: object | None = None,
) -> MaintenanceWorkflowService:
    services = inference_services or {}
    supplied_factories = factories or {}

    def factory(modality: Modality) -> Callable[[], object]:
        if modality in supplied_factories:
            return supplied_factories[modality]
        return Factory(service=services.get(modality))

    bus = event_bus or EventBus()
    return MaintenanceWorkflowService(
        machine_service=FakeMachineService(machine),  # type: ignore[arg-type]
        timeseries_inference_factory=factory(Modality.TIMESERIES),  # type: ignore[arg-type]
        audio_inference_factory=factory(Modality.AUDIO),  # type: ignore[arg-type]
        vision_inference_factory=factory(Modality.VISION),  # type: ignore[arg-type]
        thermal_inference_factory=factory(Modality.THERMAL),  # type: ignore[arg-type]
        decision_service=(  # type: ignore[arg-type]
            decision_service or DecisionService(DecisionEngine(), bus)
        ),
        evidence_package_service=evidence_service or EvidencePackageService(),
        knowledge_retriever_factory=lambda: retriever or RecordingRetriever(),  # type: ignore[return-value]
        copilot_service=MaintenanceCopilotService(
            generator=generator,
            validator=MaintenanceSafetyValidator(),
        ),
    )


def _vision_workflow(
    *,
    generator: FakeMaintenanceGenerator | None,
    question: str | None = None,
    retriever: RecordingRetriever | None = None,
    evidence_service: EvidencePackageService | None = None,
    decision_service: object | None = None,
) -> tuple[MaintenanceWorkflowService, VisionMaintenanceRequest]:
    machine = Machine(_MACHINE_ID, "PCB fixture", "pcb1")
    service = _workflow_service(
        machine=machine,
        inference_services={
            Modality.VISION: RecordingInferenceService(
                Modality.VISION,
                "visual_anomaly",
            )
        },
        retriever=retriever,
        generator=generator,
        evidence_service=evidence_service,
        decision_service=decision_service,
    )
    request = VisionMaintenanceRequest(
        machine_id=machine.id,
        content=_png_bytes(),
        intent=CopilotIntent.EXPLAIN_FINDING,
        question=question,
    )
    return service, request


def _vision_service(
    event_bus: EventBus,
    predictor: RecordingVisionPredictor,
) -> VisionInferenceService:
    orchestrator = InferenceOrchestrator(event_bus)
    orchestrator.register(
        Modality.VISION,
        predictor,
        input_type=VisionInput,
        producing_model=_model_context(Modality.VISION),
    )
    return VisionInferenceService(orchestrator, ("pcb1",))


def _model_context(modality: Modality) -> ProducingModelContext:
    return snapshot_producing_model_context(
        model_capabilities.get_runtime_default_capability(modality)
    )


def _assert_report_verifies(
    result: MaintenanceWorkflowResult,
    intent: CopilotIntent,
    *,
    question: str | None = None,
) -> None:
    request = MaintenanceCopilotRequest(
        evidence_package=result.evidence_package,
        retrieval_bundle=result.retrieval_bundle,
        intent=intent,
        question=question,
    )
    prepared = CopilotContextBuilder().build(request)
    assert verify_report_digest(result.maintenance_report)
    assert verify_maintenance_report(result.maintenance_report, prepared)
