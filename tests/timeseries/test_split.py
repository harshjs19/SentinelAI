from pathlib import Path

from modules.timeseries.data import load_bently_dataset
from modules.timeseries.split import chronological_session_split


def test_split_is_chronological_and_purged_within_each_session(
    synthetic_dataset: Path,
) -> None:
    dataset = load_bently_dataset(synthetic_dataset)

    split = chronological_session_split(
        dataset.windows,
        train_fraction=0.6,
        validation_fraction=0.2,
        purge_windows=2,
    )

    for session in dataset.windows["session"].unique():
        train = split.train.loc[split.train["session"] == session]
        validation = split.validation.loc[split.validation["session"] == session]
        test = split.test.loc[split.test["session"] == session]
        assert train["timestamp"].max() < validation["timestamp"].min()
        assert validation["timestamp"].max() < test["timestamp"].min()
        assert len(train) + len(validation) + len(test) == 32

    expected_labels = set(dataset.windows["label"])
    assert set(split.train["label"]) == expected_labels
    assert set(split.validation["label"]) == expected_labels
    assert set(split.test["label"]) == expected_labels
