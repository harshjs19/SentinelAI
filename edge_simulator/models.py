from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Modality(StrEnum):
    TIMESERIES = "timeseries"
    AUDIO = "audio"
    VISION = "vision"
    THERMAL = "thermal"


class InputLabel(StrEnum):
    SIMULATED = "SIMULATED INPUT"
    RECORDED_REPLAY = "RECORDED REPLAY"
    PHYSICAL_LIVE_SENSOR = "PHYSICAL LIVE SENSOR"


@dataclass(frozen=True)
class TimeseriesSample:
    ch1_bias: float
    ch1_derivedPk: float
    ch1_direct: float
    ch1_directRMS: float
    ch1_velocityPk: float
    ch1_velocityRMS: float

    def to_api_payload(self) -> dict[str, float]:
        return {
            "ch1_bias": self.ch1_bias,
            "ch1_derivedPk": self.ch1_derivedPk,
            "ch1_direct": self.ch1_direct,
            "ch1_directRMS": self.ch1_directRMS,
            "ch1_velocityPk": self.ch1_velocityPk,
            "ch1_velocityRMS": self.ch1_velocityRMS,
        }


@dataclass(frozen=True)
class EdgeObservation:
    """One single-modality payload prepared for the public HTTP API."""

    modality: Modality
    input_label: InputLabel
    samples: tuple[TimeseriesSample, ...] = ()
    asset_path: Path | None = None
    content_type: str | None = None

    def __post_init__(self) -> None:
        if self.input_label is InputLabel.PHYSICAL_LIVE_SENSOR:
            raise ValueError("Physical live sensor input is not supported by this simulator")
        has_samples = bool(self.samples)
        has_asset = self.asset_path is not None
        if has_samples == has_asset:
            raise ValueError("An edge observation must contain exactly one modality payload")
        if has_samples and self.modality is not Modality.TIMESERIES:
            raise ValueError("Time-series samples require the time-series modality")
        if has_asset and self.modality is Modality.TIMESERIES:
            raise ValueError("Time-series observations cannot contain media assets")
        if has_samples and self.input_label is not InputLabel.SIMULATED:
            raise ValueError("Synthetic time-series observations must be labelled SIMULATED INPUT")
        if has_asset and self.input_label is not InputLabel.RECORDED_REPLAY:
            raise ValueError("Media observations must be labelled RECORDED REPLAY")
        if has_asset and not self.content_type:
            raise ValueError("Media observations require a content type")


@dataclass(frozen=True)
class MachineRecord:
    machine_id: str
    name: str
    asset_type: str


@dataclass(frozen=True)
class SubmissionReceipt:
    status_code: int
    report_id: str
    replayed: bool
    idempotency_key: str = field(repr=False)
    document: dict[str, object] = field(repr=False)


@dataclass(frozen=True)
class ScenarioOutcome:
    scenario_name: str
    observation: EdgeObservation
    receipt: SubmissionReceipt
    notes: tuple[str, ...] = ()
