from collections.abc import Callable, Mapping
from typing import Any

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

LOGISTIC_REGRESSION = "logistic_regression"
RANDOM_FOREST = "random_forest"
CANDIDATE_NAMES = (LOGISTIC_REGRESSION, RANDOM_FOREST)


def build_candidate(name: str, random_seed: int = 42) -> Pipeline:
    if name == LOGISTIC_REGRESSION:
        return Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(max_iter=2_000, random_state=random_seed),
                ),
            ]
        )
    if name == RANDOM_FOREST:
        return Pipeline(
            [
                (
                    "classifier",
                    RandomForestClassifier(
                        n_estimators=300,
                        random_state=random_seed,
                        n_jobs=-1,
                    ),
                )
            ]
        )
    raise ValueError(f"Unknown Thermal candidate model: {name}")


def candidate_factories(random_seed: int = 42) -> dict[str, Callable[[], Pipeline]]:
    return {
        name: (lambda candidate=name: build_candidate(candidate, random_seed))
        for name in CANDIDATE_NAMES
    }


def select_candidate(validation_metrics: Mapping[str, Mapping[str, Any]]) -> str:
    if set(validation_metrics) != set(CANDIDATE_NAMES):
        raise ValueError("Validation metrics must include both Thermal candidates")
    return max(
        CANDIDATE_NAMES,
        key=lambda name: (
            float(validation_metrics[name]["macro_f1"]),
            float(validation_metrics[name]["balanced_accuracy"]),
            -CANDIDATE_NAMES.index(name),
        ),
    )


def model_parameters(model: Pipeline) -> dict[str, object]:
    classifier = model.named_steps["classifier"]
    if isinstance(classifier, LogisticRegression):
        return {
            "pipeline": ["StandardScaler", "LogisticRegression"],
            "max_iter": classifier.max_iter,
            "random_state": classifier.random_state,
            "solver": classifier.solver,
        }
    if isinstance(classifier, RandomForestClassifier):
        return {
            "pipeline": ["RandomForestClassifier"],
            "n_estimators": classifier.n_estimators,
            "random_state": classifier.random_state,
            "n_jobs": classifier.n_jobs,
        }
    raise ValueError("Unsupported Thermal classifier pipeline")
