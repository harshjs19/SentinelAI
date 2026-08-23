import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from modules.timeseries.config import FEATURE_NAMES, RAW_FEATURES

SESSION_FILES = (
    "Combined_Baseline1.csv",
    "Combined_Baseline2.csv",
    "Combined_BentShaft.csv",
    "Combined_EccentricRotor.csv",
    "Combined_FaultedBearing.csv",
    "Combined_FaultedCoupling.csv",
    "Combined_Imbalance.csv",
)

LABEL_MAPPING = {
    "baseline": "healthy",
    "healthy": "healthy",
    "eccentric_rotor": "eccentric_rotor",
    "bent_shaft": "bent_shaft",
    "faulted_bearing": "bearing_fault",
    "bearing_fault": "bearing_fault",
    "faulted_coupling": "coupling_fault",
    "coupling_fault": "coupling_fault",
    "imbalance": "imbalance",
}


@dataclass(frozen=True)
class TimeseriesDataset:
    windows: pd.DataFrame
    raw_rows: int
    dropped_timestamp_rows: int


def normalize_label(value: str) -> str:
    normalized = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.strip().lower()))
    try:
        return LABEL_MAPPING[normalized]
    except KeyError as error:
        raise ValueError(f"Unknown time-series label: {value}") from error


def extract_window_features(window: pd.DataFrame) -> dict[str, float]:
    missing = set(RAW_FEATURES) - set(window.columns)
    if missing:
        raise ValueError(f"Missing raw features: {', '.join(sorted(missing))}")

    numeric = window.loc[:, RAW_FEATURES].apply(pd.to_numeric, errors="coerce")
    features: dict[str, float] = {}
    for feature in RAW_FEATURES:
        features[f"{feature}_mean"] = float(numeric[feature].mean())
        features[f"{feature}_std"] = float(numeric[feature].std())
    return features


def build_measurement_windows(rows: pd.DataFrame) -> pd.DataFrame:
    required = {"session", "timestamp", "label", *RAW_FEATURES}
    missing = required - set(rows.columns)
    if missing:
        raise ValueError(f"Missing dataset columns: {', '.join(sorted(missing))}")

    grouped = rows.groupby(["session", "timestamp", "label"], as_index=False)[
        list(RAW_FEATURES)
    ].agg(["mean", "std"])
    grouped.columns = ["session", "timestamp", "label", *FEATURE_NAMES]
    return grouped.sort_values(["session", "timestamp"], ignore_index=True)


def load_bently_dataset(dataset_root: Path) -> TimeseriesDataset:
    combined_files = dataset_root / "CombinedFiles"
    frames: list[pd.DataFrame] = []
    raw_rows = 0
    dropped_timestamp_rows = 0

    for filename in SESSION_FILES:
        path = combined_files / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing Bently Nevada recording: {path}")

        frame = pd.read_csv(path)
        required = {"timestamp", "status", *RAW_FEATURES}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{path.name} is missing columns: {', '.join(sorted(missing))}")

        raw_rows += len(frame)
        frame["timestamp"] = pd.to_datetime(
            frame["timestamp"], format="%m/%d/%Y %H:%M", errors="coerce"
        )
        dropped_timestamp_rows += int(frame["timestamp"].isna().sum())
        frame = frame.dropna(subset=["timestamp"]).copy()
        frame["label"] = frame["status"].map(normalize_label)
        frame["session"] = path.stem.removeprefix("Combined_").lower()
        for feature in RAW_FEATURES:
            frame[feature] = pd.to_numeric(frame[feature], errors="coerce")
        frames.append(frame.loc[:, ["session", "timestamp", "label", *RAW_FEATURES]])

    rows = pd.concat(frames, ignore_index=True)
    return TimeseriesDataset(
        windows=build_measurement_windows(rows),
        raw_rows=raw_rows,
        dropped_timestamp_rows=dropped_timestamp_rows,
    )
