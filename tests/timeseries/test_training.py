import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from ai_core.predictor import Predictor
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from modules.timeseries.artifact import load_artifact
from modules.timeseries.config import FEATURE_NAMES, TimeseriesTrainingConfig
from modules.timeseries.data import load_bently_dataset
from modules.timeseries.predictor import TimeseriesPredictor
from modules.timeseries.training import evaluate_saved_artifact, train_timeseries


@pytest.fixture
def trained_predictor(
    synthetic_dataset: Path,
    tmp_path: Path,
) -> tuple[TimeseriesPredictor, TimeseriesTrainingConfig]:
    config = TimeseriesTrainingConfig(
        dataset_root=synthetic_dataset,
        artifact_path=tmp_path / "model.joblib",
        evaluation_path=tmp_path / "evaluation.json",
        purge_windows=2,
        random_forest_estimators=20,
    )
    outcome = train_timeseries(config)

    assert outcome.selected_model in {"logistic_regression", "random_forest"}
    assert config.artifact_path.is_file()
    assert config.artifact_path.with_suffix(".metadata.json").is_file()
    assert config.evaluation_path.is_file()
    results = json.loads(config.evaluation_path.read_text(encoding="utf-8"))
    assert set(results["validation"]) == {"logistic_regression", "random_forest"}
    assert results["selection_metric"] == "validation_macro_f1"
    assert results["final_fit"] == {
        "partitions": ["train", "validation"],
        "windows": 182,
    }
    return TimeseriesPredictor(config.artifact_path), config


def test_trains_loads_and_maps_prediction_to_domain(
    trained_predictor: tuple[TimeseriesPredictor, TimeseriesTrainingConfig],
    synthetic_dataset: Path,
) -> None:
    predictor, config = trained_predictor
    predictor_contract: Predictor[Mapping[str, float]] = predictor
    dataset = load_bently_dataset(synthetic_dataset)
    features = dataset.windows.iloc[0].loc[list(FEATURE_NAMES)].to_dict()

    prediction = predictor_contract.predict(features)
    probabilities = predictor.predict_probabilities(features)
    evaluation = evaluate_saved_artifact(config)

    assert isinstance(prediction, Prediction)
    assert prediction.modality is Modality.TIMESERIES
    assert prediction.label in probabilities
    assert 0 <= prediction.confidence <= 1
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert 0 <= evaluation.macro_f1 <= 1


def test_predictor_requires_complete_feature_set(
    trained_predictor: tuple[TimeseriesPredictor, TimeseriesTrainingConfig],
) -> None:
    predictor, _ = trained_predictor

    with pytest.raises(ValueError, match="Missing model features"):
        predictor.predict({"ch1_bias_mean": 0.0})


def test_artifact_evaluation_uses_saved_split_metadata(
    trained_predictor: tuple[TimeseriesPredictor, TimeseriesTrainingConfig],
) -> None:
    _, training_config = trained_predictor
    artifact = load_artifact(training_config.artifact_path)
    expected = evaluate_saved_artifact(training_config)
    conflicting_config = TimeseriesTrainingConfig(
        dataset_root=training_config.dataset_root,
        artifact_path=training_config.artifact_path,
        evaluation_path=training_config.evaluation_path,
        train_fraction=0.5,
        validation_fraction=0.25,
        purge_windows=0,
        random_forest_estimators=training_config.random_forest_estimators,
    )

    actual = evaluate_saved_artifact(conflicting_config)

    assert artifact.metadata.format_version == 2
    assert artifact.metadata.train_fraction == 0.6
    assert artifact.metadata.validation_fraction == 0.2
    assert artifact.metadata.purge_windows == 2
    assert actual == expected
