from pathlib import Path

import pandas as pd
import pytest

from modules.timeseries.config import FEATURE_NAMES, RAW_FEATURES
from modules.timeseries.data import (
    extract_window_features,
    load_bently_dataset,
    normalize_label,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("baseline", "healthy"),
        (" Faulted Bearing ", "bearing_fault"),
        ("faulted-coupling", "coupling_fault"),
        ("Eccentric Rotor", "eccentric_rotor"),
    ],
)
def test_normalizes_labels(raw: str, expected: str) -> None:
    assert normalize_label(raw) == expected


def test_rejects_unknown_label() -> None:
    with pytest.raises(ValueError, match="Unknown time-series label"):
        normalize_label("mystery_fault")


def test_loads_recordings_as_measurement_windows(synthetic_dataset: Path) -> None:
    dataset = load_bently_dataset(synthetic_dataset)

    assert dataset.raw_rows == 7 * 36 * 3
    assert len(dataset.windows) == 7 * 36
    assert set(dataset.windows["label"]) == {
        "healthy",
        "eccentric_rotor",
        "bent_shaft",
        "bearing_fault",
        "coupling_fault",
        "imbalance",
    }
    assert set(FEATURE_NAMES).issubset(dataset.windows.columns)
    assert "volts" not in dataset.windows
    assert dataset.windows.loc[:, FEATURE_NAMES].isna().any().any()


def test_extracts_window_statistics() -> None:
    window = pd.DataFrame({feature: [1.0, 3.0] for feature in RAW_FEATURES})

    features = extract_window_features(window)

    assert set(features) == set(FEATURE_NAMES)
    assert features["ch1_bias_mean"] == 2.0
    assert features["ch1_bias_std"] == pytest.approx(2**0.5)
