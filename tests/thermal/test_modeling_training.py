from collections.abc import Callable

import numpy as np

from modules.thermal.config import CONDITION_LABELS
from modules.thermal.embedding_cache import ThermalEmbeddingData
from modules.thermal.modeling import (
    LOGISTIC_REGRESSION,
    RANDOM_FOREST,
    build_candidate,
    select_candidate,
)
from modules.thermal.training import fit_select_refit

LABELS = tuple(CONDITION_LABELS.values())


def synthetic_data() -> ThermalEmbeddingData:
    embeddings: list[np.ndarray] = []
    labels: list[str] = []
    speeds: list[str] = []
    experiments: list[str] = []
    for speed in ("F5", "F15", "F50", "F60"):
        for index, label in enumerate(LABELS):
            embedding = np.zeros(512, dtype=np.float64)
            embedding[0] = index
            embeddings.append(embedding)
            labels.append(label)
            speeds.append(speed)
            experiments.append(f"{label}_{speed}")
    rows = len(labels)
    return ThermalEmbeddingData(
        embeddings=np.stack(embeddings),
        labels=np.asarray(labels),
        raw_conditions=np.asarray(["raw"] * rows),
        speeds=np.asarray(speeds),
        rpms=np.zeros(rows, dtype=np.int64),
        experiment_ids=np.asarray(experiments),
        relative_files=np.asarray(["metadata-only.mat"] * rows),
        frame_indices=np.ones(rows, dtype=np.int64),
        audit={"missing_frames": 0, "corrupt_frames": 0},
        cache_hit=False,
        extraction_seconds=0.0,
    )


class RecordingClassifier:
    def __init__(self, correct: bool) -> None:
        self.correct = correct
        self.fit_rows: list[int] = []
        self.predict_rows: list[int] = []
        self.classes_: np.ndarray = np.asarray([], dtype=np.str_)

    def fit(self, features: np.ndarray, labels: np.ndarray) -> "RecordingClassifier":
        self.fit_rows.append(len(features))
        self.classes_ = np.unique(labels)
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        self.predict_rows.append(len(features))
        probabilities = np.full((len(features), len(self.classes_)), 0.001, dtype=np.float64)
        for row, feature in enumerate(features):
            label = LABELS[int(feature[0])] if self.correct else LABELS[0]
            probabilities[row, list(self.classes_).index(label)] = 1.0
        return probabilities / probabilities.sum(axis=1, keepdims=True)


def recording_factory(correct: bool, instances: list[RecordingClassifier]) -> Callable[[], object]:
    def factory() -> RecordingClassifier:
        model = RecordingClassifier(correct)
        instances.append(model)
        return model

    return factory


def test_builds_both_fixed_candidate_pipelines() -> None:
    logistic = build_candidate(LOGISTIC_REGRESSION)
    forest = build_candidate(RANDOM_FOREST)

    assert list(logistic.named_steps) == ["scaler", "classifier"]
    assert logistic.named_steps["classifier"].max_iter == 2_000
    assert list(forest.named_steps) == ["classifier"]
    assert forest.named_steps["classifier"].n_estimators == 300
    assert forest.named_steps["classifier"].random_state == 42


def test_selects_by_macro_f1_then_balanced_accuracy() -> None:
    selected = select_candidate(
        {
            LOGISTIC_REGRESSION: {"macro_f1": 0.7, "balanced_accuracy": 0.8},
            RANDOM_FOREST: {"macro_f1": 0.8, "balanced_accuracy": 0.7},
        }
    )
    tied = select_candidate(
        {
            LOGISTIC_REGRESSION: {"macro_f1": 0.8, "balanced_accuracy": 0.7},
            RANDOM_FOREST: {"macro_f1": 0.8, "balanced_accuracy": 0.9},
        }
    )

    assert selected == RANDOM_FOREST
    assert tied == RANDOM_FOREST


def test_final_model_is_freshly_refit_on_train_plus_validation_only() -> None:
    logistic_instances: list[RecordingClassifier] = []
    forest_instances: list[RecordingClassifier] = []
    result = fit_select_refit(
        synthetic_data(),
        {
            LOGISTIC_REGRESSION: recording_factory(False, logistic_instances),
            RANDOM_FOREST: recording_factory(True, forest_instances),
        },
    )

    assert result.selected_model == RANDOM_FOREST
    assert len(logistic_instances) == 1
    assert len(forest_instances) == 2
    assert result.final_model is forest_instances[1]
    assert logistic_instances[0].fit_rows == [18]
    assert forest_instances[0].fit_rows == [18]
    assert forest_instances[1].fit_rows == [27]
    assert logistic_instances[0].predict_rows == [9]
    assert forest_instances[0].predict_rows == [9]
    assert forest_instances[1].predict_rows == [9]
    assert result.final_test_metrics["accuracy"] == 1.0
    assert result.experiment_test_metrics["experiment_count"] == 9
    assert synthetic_data().embeddings.shape[1] == 512
