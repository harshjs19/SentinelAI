from pathlib import Path

import pytest

from edge_simulator.config import API_BASE_URL_ENV, DEFAULT_API_BASE_URL, SimulatorConfig
from edge_simulator.models import EdgeObservation, InputLabel, Modality, TimeseriesSample
from edge_simulator.scenarios import SCENARIOS, build_source, list_scenarios
from edge_simulator.sources.media import (
    ReplayAudioSource,
    ReplayThermalSource,
    ReplayVisionSource,
)
from edge_simulator.sources.timeseries import SimulatedTimeSeriesSource

EXPECTED_SAMPLE_KEYS = {
    "ch1_bias",
    "ch1_derivedPk",
    "ch1_direct",
    "ch1_directRMS",
    "ch1_velocityPk",
    "ch1_velocityRMS",
}


def test_config_uses_default_and_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_BASE_URL_ENV, raising=False)
    assert SimulatorConfig.from_environment().api_base_url == DEFAULT_API_BASE_URL

    monkeypatch.setenv(API_BASE_URL_ENV, "https://sentinel.example.test/api/")
    assert SimulatorConfig.from_environment().api_base_url == "https://sentinel.example.test/api"


@pytest.mark.parametrize(
    "url",
    ["localhost:8000", "ftp://example.test", "http://example.test?token=secret"],
)
def test_config_rejects_invalid_api_urls(url: str) -> None:
    with pytest.raises(ValueError, match="URL"):
        SimulatorConfig(api_base_url=url)


def test_timeout_configuration_is_centralized() -> None:
    timeout = SimulatorConfig().httpx_timeout()
    assert timeout.connect == 3.0
    assert timeout.read == 120.0
    assert timeout.write == 30.0
    assert timeout.pool == 5.0


def test_time_series_source_is_deterministic_bounded_and_schema_exact() -> None:
    first = SimulatedTimeSeriesSource("healthy").capture()
    second = SimulatedTimeSeriesSource("healthy").capture()

    assert first == second
    assert first.input_label is InputLabel.SIMULATED
    assert first.modality is Modality.TIMESERIES
    assert len(first.samples) == 24
    for sample in first.samples:
        payload = sample.to_api_payload()
        assert set(payload) == EXPECTED_SAMPLE_KEYS
        assert all(-25.0 <= value <= 25.0 for value in payload.values())


def test_time_series_profiles_differ_without_encoding_an_expected_output() -> None:
    healthy = SimulatedTimeSeriesSource("healthy").capture()
    fault_demo = SimulatedTimeSeriesSource("fault_demo").capture()

    assert healthy.samples != fault_demo.samples
    assert not hasattr(healthy, "expected_prediction")
    assert not hasattr(fault_demo, "expected_prediction")


@pytest.mark.parametrize("sample_count", [1, 257])
def test_time_series_source_enforces_bounded_sample_count(sample_count: int) -> None:
    with pytest.raises(ValueError, match="between 2 and 256"):
        SimulatedTimeSeriesSource("healthy", sample_count=sample_count)


@pytest.mark.parametrize(
    ("source_type", "suffix", "expected_modality", "expected_content_type"),
    [
        (ReplayAudioSource, ".wav", Modality.AUDIO, "audio/wav"),
        (ReplayVisionSource, ".png", Modality.VISION, "image/png"),
        (ReplayThermalSource, ".jpg", Modality.THERMAL, "image/jpeg"),
    ],
)
def test_media_sources_label_explicit_local_assets_as_recorded_replay(
    tmp_path: Path,
    source_type: type[ReplayAudioSource | ReplayVisionSource | ReplayThermalSource],
    suffix: str,
    expected_modality: Modality,
    expected_content_type: str,
) -> None:
    asset = tmp_path / f"local{suffix}"
    asset.write_bytes(b"recorded replay fixture")

    observation = source_type(asset).capture()

    assert observation.input_label is InputLabel.RECORDED_REPLAY
    assert observation.modality is expected_modality
    assert observation.content_type == expected_content_type
    assert observation.asset_path == asset


def test_media_source_fails_cleanly_for_missing_and_unsupported_assets(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="was not found"):
        ReplayAudioSource(tmp_path / "missing.wav").capture()

    unsupported = tmp_path / "asset.mp3"
    unsupported.write_bytes(b"not accepted")
    with pytest.raises(ValueError, match="unsupported"):
        ReplayAudioSource(unsupported).capture()


def test_observation_enforces_single_modality_and_rejects_physical_live_sensor() -> None:
    sample = TimeseriesSample(0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
    with pytest.raises(ValueError, match="exactly one modality"):
        EdgeObservation(Modality.TIMESERIES, InputLabel.SIMULATED)
    with pytest.raises(ValueError, match="exactly one modality"):
        EdgeObservation(
            Modality.TIMESERIES,
            InputLabel.SIMULATED,
            samples=(sample,),
            asset_path=Path("asset.wav"),
            content_type="audio/wav",
        )
    with pytest.raises(ValueError, match="not supported"):
        EdgeObservation(
            Modality.TIMESERIES,
            InputLabel.PHYSICAL_LIVE_SENSOR,
            samples=(sample,),
        )


def test_registry_contains_only_the_required_labelled_scenarios() -> None:
    expected = {
        "timeseries_healthy",
        "timeseries_fault_demo",
        "audio_replay",
        "vision_replay",
        "thermal_replay",
        "idempotent_replay",
        "high_impact_safe_request",
        "provider_unavailable_fallback",
    }
    assert set(SCENARIOS) == expected
    assert [item.name for item in list_scenarios()] == sorted(expected)
    assert all(
        item.input_label in {InputLabel.SIMULATED, InputLabel.RECORDED_REPLAY}
        for item in SCENARIOS.values()
    )
    assert SCENARIOS["provider_unavailable_fallback"].intent == "summarize_analysis"


def test_registry_builds_media_only_with_an_explicit_asset(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires --asset"):
        build_source(SCENARIOS["audio_replay"], None)
    assert isinstance(
        build_source(SCENARIOS["vision_replay"], tmp_path / "image.png"),
        ReplayVisionSource,
    )
