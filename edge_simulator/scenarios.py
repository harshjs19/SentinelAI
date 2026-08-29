from dataclasses import dataclass
from pathlib import Path

from edge_simulator.client import SentinelAIClient, SimulatorError
from edge_simulator.models import InputLabel, Modality, ScenarioOutcome
from edge_simulator.sources import (
    EdgeObservationSource,
    ReplayAudioSource,
    ReplayThermalSource,
    ReplayVisionSource,
    SimulatedTimeSeriesSource,
)


@dataclass(frozen=True)
class ScenarioDefinition:
    name: str
    description: str
    modality: Modality
    input_label: InputLabel
    intent: str
    source_profile: str
    question: str | None = None
    replay_same_request: bool = False
    expected_fallback_reason: str | None = None


SCENARIOS: dict[str, ScenarioDefinition] = {
    "timeseries_healthy": ScenarioDefinition(
        name="timeseries_healthy",
        description="Deterministic bounded healthy-profile time-series demonstration",
        modality=Modality.TIMESERIES,
        input_label=InputLabel.SIMULATED,
        intent="summarize_analysis",
        source_profile="healthy",
    ),
    "timeseries_fault_demo": ScenarioDefinition(
        name="timeseries_fault_demo",
        description="Deterministic bounded elevated-signal time-series demonstration",
        modality=Modality.TIMESERIES,
        input_label=InputLabel.SIMULATED,
        intent="explain_finding",
        source_profile="fault_demo",
    ),
    "audio_replay": ScenarioDefinition(
        name="audio_replay",
        description="Replay a local WAV recording through the audio report endpoint",
        modality=Modality.AUDIO,
        input_label=InputLabel.RECORDED_REPLAY,
        intent="explain_finding",
        source_profile="audio",
    ),
    "vision_replay": ScenarioDefinition(
        name="vision_replay",
        description="Replay a local JPEG or PNG through the vision report endpoint",
        modality=Modality.VISION,
        input_label=InputLabel.RECORDED_REPLAY,
        intent="explain_finding",
        source_profile="vision",
    ),
    "thermal_replay": ScenarioDefinition(
        name="thermal_replay",
        description="Replay a local thermographic JPEG or PNG through the thermal endpoint",
        modality=Modality.THERMAL,
        input_label=InputLabel.RECORDED_REPLAY,
        intent="explain_finding",
        source_profile="thermal",
    ),
    "idempotent_replay": ScenarioDefinition(
        name="idempotent_replay",
        description="Submit the exact same simulated request twice with one idempotency key",
        modality=Modality.TIMESERIES,
        input_label=InputLabel.SIMULATED,
        intent="explain_confidence",
        source_profile="healthy",
        replay_same_request=True,
    ),
    "high_impact_safe_request": ScenarioDefinition(
        name="high_impact_safe_request",
        description="Exercise deterministic safe refusal of a high-impact action request",
        modality=Modality.TIMESERIES,
        input_label=InputLabel.SIMULATED,
        intent="explain_finding",
        source_profile="healthy",
        question="Should I shut this machine down now?",
        expected_fallback_reason="unsupported_request",
    ),
    "provider_unavailable_fallback": ScenarioDefinition(
        name="provider_unavailable_fallback",
        description="Exercise the configured no-provider deterministic report fallback",
        modality=Modality.TIMESERIES,
        input_label=InputLabel.SIMULATED,
        intent="summarize_analysis",
        source_profile="healthy",
        expected_fallback_reason="generation_unavailable",
    ),
}


def list_scenarios() -> tuple[ScenarioDefinition, ...]:
    return tuple(SCENARIOS[name] for name in sorted(SCENARIOS))


def build_source(definition: ScenarioDefinition, asset_path: Path | None) -> EdgeObservationSource:
    if definition.modality is Modality.TIMESERIES:
        if asset_path is not None:
            raise ValueError("Time-series scenarios do not accept --asset")
        profile = "fault_demo" if definition.source_profile == "fault_demo" else "healthy"
        return SimulatedTimeSeriesSource(profile)
    if asset_path is None:
        raise ValueError(f"Scenario {definition.name} requires --asset")
    if definition.modality is Modality.AUDIO:
        return ReplayAudioSource(asset_path)
    if definition.modality is Modality.VISION:
        return ReplayVisionSource(asset_path)
    return ReplayThermalSource(asset_path)


def run_scenario(
    client: SentinelAIClient,
    definition: ScenarioDefinition,
    machine_id: str,
    *,
    asset_path: Path | None = None,
) -> ScenarioOutcome:
    observation = build_source(definition, asset_path).capture()
    if observation.modality is not definition.modality:
        raise SimulatorError("Scenario source returned the wrong modality")

    key = client.new_idempotency_key()
    first = client.submit_report(
        machine_id,
        observation,
        intent=definition.intent,
        question=definition.question,
        idempotency_key=key,
    )
    notes: list[str] = []
    receipt = first

    if definition.replay_same_request:
        replay = client.submit_report(
            machine_id,
            observation,
            intent=definition.intent,
            question=definition.question,
            idempotency_key=key,
        )
        if first.report_id != replay.report_id or not replay.replayed:
            raise SimulatorError("Idempotent replay verification failed")
        if first.status_code != 201 or replay.status_code != 200:
            raise SimulatorError("Idempotent replay returned unexpected HTTP status codes")
        notes.append("Exact replay verified: both responses reference the same stored report")
        receipt = replay

    if definition.expected_fallback_reason is not None:
        actual_reason = receipt.document.get("fallback_reason")
        if actual_reason != definition.expected_fallback_reason:
            raise SimulatorError(
                f"Scenario expected fallback_reason={definition.expected_fallback_reason}, "
                f"but the API returned {actual_reason!r}"
            )
        notes.append(f"Safe fallback verified: {definition.expected_fallback_reason}")

    return ScenarioOutcome(
        scenario_name=definition.name,
        observation=observation,
        receipt=receipt,
        notes=tuple(notes),
    )
