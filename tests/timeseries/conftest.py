from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.timeseries.config import RAW_FEATURES
from modules.timeseries.data import SESSION_FILES

RAW_LABELS = {
    "Combined_Baseline1.csv": "baseline",
    "Combined_Baseline2.csv": "baseline",
    "Combined_BentShaft.csv": "bent_shaft",
    "Combined_EccentricRotor.csv": "eccentric_rotor",
    "Combined_FaultedBearing.csv": "faulted_bearing",
    "Combined_FaultedCoupling.csv": "faulted_coupling",
    "Combined_Imbalance.csv": "imbalance",
}

CLASS_CENTERS = {
    "baseline": 0.0,
    "eccentric_rotor": 3.0,
    "bent_shaft": 6.0,
    "faulted_bearing": 9.0,
    "faulted_coupling": 12.0,
    "imbalance": 15.0,
}


@pytest.fixture
def synthetic_dataset(tmp_path: Path) -> Iterator[Path]:
    combined_files = tmp_path / "CombinedFiles"
    combined_files.mkdir()
    random = np.random.default_rng(42)
    start = datetime(2025, 1, 1, 9, 0)

    for session_index, filename in enumerate(SESSION_FILES):
        label = RAW_LABELS[filename]
        center = CLASS_CENTERS[label]
        rows: list[dict[str, object]] = []
        for minute in range(36):
            timestamp = start + timedelta(days=session_index, minutes=minute)
            for sample in range(3):
                row: dict[str, object] = {
                    "timestamp": timestamp.strftime("%m/%d/%Y %H:%M"),
                    "status": label,
                    "volts": 45 if label == "faulted_bearing" else 50,
                }
                for feature_index, feature in enumerate(RAW_FEATURES):
                    row[feature] = center + feature_index * 0.1 + random.normal(0, 0.03)
                if filename == "Combined_Baseline1.csv" and minute == 2:
                    row["ch1_direct"] = np.nan
                rows.append(row)
        pd.DataFrame(rows).to_csv(combined_files / filename, index=False)

    yield tmp_path
