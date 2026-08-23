from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TimeseriesSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    strategy: str


def chronological_session_split(
    windows: pd.DataFrame,
    *,
    train_fraction: float,
    validation_fraction: float,
    purge_windows: int,
) -> TimeseriesSplit:
    if train_fraction <= 0 or validation_fraction <= 0:
        raise ValueError("Split fractions must be positive")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("Train and validation fractions must leave a test partition")
    if purge_windows < 0:
        raise ValueError("Purge windows cannot be negative")

    partitions: dict[str, list[pd.DataFrame]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    for session, session_rows in windows.groupby("session", sort=True):
        ordered = session_rows.sort_values("timestamp")
        row_count = len(ordered)
        train_end = int(row_count * train_fraction)
        validation_end = int(row_count * (train_fraction + validation_fraction))
        validation_start = train_end + purge_windows
        test_start = validation_end + purge_windows

        session_partitions = {
            "train": ordered.iloc[:train_end],
            "validation": ordered.iloc[validation_start:validation_end],
            "test": ordered.iloc[test_start:],
        }
        if any(partition.empty for partition in session_partitions.values()):
            raise ValueError(f"Session {session} is too short for the configured split")
        for name, partition in session_partitions.items():
            partitions[name].append(partition)

    combined = {
        name: pd.concat(parts, ignore_index=True).sort_values(
            ["session", "timestamp"], ignore_index=True
        )
        for name, parts in partitions.items()
    }
    label_sets = {name: set(frame["label"]) for name, frame in combined.items()}
    if len({frozenset(labels) for labels in label_sets.values()}) != 1:
        raise ValueError(f"Every split must contain the same labels: {label_sets}")

    return TimeseriesSplit(
        train=combined["train"],
        validation=combined["validation"],
        test=combined["test"],
        strategy=(
            "Per-recording blocked chronological "
            f"{train_fraction:.0%}/{validation_fraction:.0%}/"
            f"{1 - train_fraction - validation_fraction:.0%} split with timestamp windows "
            f"kept intact and {purge_windows} windows purged at each boundary"
        ),
    )
