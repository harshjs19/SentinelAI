import math
from typing import Literal

from edge_simulator.models import EdgeObservation, InputLabel, Modality, TimeseriesSample
from edge_simulator.sources.base import EdgeObservationSource

TimeSeriesProfile = Literal["healthy", "fault_demo"]


class SimulatedTimeSeriesSource(EdgeObservationSource):
    """Generate deterministic, bounded channel-1 raw measurements."""

    def __init__(self, profile: TimeSeriesProfile, sample_count: int = 24) -> None:
        if profile not in {"healthy", "fault_demo"}:
            raise ValueError(f"Unknown time-series simulation profile: {profile}")
        if not 2 <= sample_count <= 256:
            raise ValueError("Time-series sample count must be between 2 and 256")
        self._profile = profile
        self._sample_count = sample_count

    def capture(self) -> EdgeObservation:
        samples = tuple(self._sample(index) for index in range(self._sample_count))
        return EdgeObservation(
            modality=Modality.TIMESERIES,
            input_label=InputLabel.SIMULATED,
            samples=samples,
        )

    def _sample(self, index: int) -> TimeseriesSample:
        phase = 2 * math.pi * index / self._sample_count
        if self._profile == "healthy":
            return TimeseriesSample(
                ch1_bias=_bounded(-11.98 + 0.025 * math.sin(phase)),
                ch1_derivedPk=_bounded(0.18 + 0.035 * math.cos(phase)),
                ch1_direct=_bounded(0.73 + 0.045 * math.sin(phase + 0.3)),
                ch1_directRMS=_bounded(0.13 + 0.018 * math.cos(phase + 0.4)),
                ch1_velocityPk=_bounded(0.063 + 0.007 * math.sin(phase + 0.8)),
                ch1_velocityRMS=_bounded(0.016 + 0.003 * math.cos(phase + 0.5)),
            )
        return TimeseriesSample(
            ch1_bias=_bounded(-8.1 + 0.35 * math.sin(phase)),
            ch1_derivedPk=_bounded(2.7 + 0.42 * math.cos(phase)),
            ch1_direct=_bounded(4.2 + 0.55 * math.sin(phase + 0.3)),
            ch1_directRMS=_bounded(1.8 + 0.28 * math.cos(phase + 0.4)),
            ch1_velocityPk=_bounded(0.92 + 0.16 * math.sin(phase + 0.8)),
            ch1_velocityRMS=_bounded(0.61 + 0.09 * math.cos(phase + 0.5)),
        )


def _bounded(value: float) -> float:
    return round(max(-25.0, min(25.0, value)), 6)
