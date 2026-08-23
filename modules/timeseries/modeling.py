import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ai_core.evaluation import ClassificationEvaluation
from modules.timeseries.config import TimeseriesTrainingConfig


def build_candidates(config: TimeseriesTrainingConfig) -> dict[str, Pipeline]:
    return {
        "logistic_regression": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        class_weight="balanced",
                        max_iter=2_000,
                        random_state=config.random_seed,
                    ),
                ),
            ]
        ),
        "random_forest": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "classifier",
                    RandomForestClassifier(
                        n_estimators=config.random_forest_estimators,
                        min_samples_leaf=2,
                        class_weight="balanced_subsample",
                        random_state=config.random_seed,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
    }


def model_parameters(name: str, config: TimeseriesTrainingConfig) -> dict[str, object]:
    if name == "logistic_regression":
        return {
            "class_weight": "balanced",
            "max_iter": 2_000,
            "random_state": config.random_seed,
        }
    if name == "random_forest":
        return {
            "n_estimators": config.random_forest_estimators,
            "min_samples_leaf": 2,
            "class_weight": "balanced_subsample",
            "random_state": config.random_seed,
            "n_jobs": -1,
        }
    raise ValueError(f"Unknown model: {name}")


def evaluate_classifier(
    model: Pipeline,
    features: pd.DataFrame,
    labels: pd.Series,
    class_names: tuple[str, ...],
) -> ClassificationEvaluation:
    predictions = model.predict(features)
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels,
        predictions,
        average="macro",
        zero_division=0,
    )
    report = classification_report(
        labels,
        predictions,
        labels=list(class_names),
        output_dict=True,
        zero_division=0,
    )
    per_class = {
        class_name: {
            metric: float(report[class_name][metric])
            for metric in ("precision", "recall", "f1-score", "support")
        }
        for class_name in class_names
    }
    matrix = confusion_matrix(labels, predictions, labels=list(class_names))
    return ClassificationEvaluation(
        labels=class_names,
        accuracy=float(accuracy_score(labels, predictions)),
        balanced_accuracy=float(balanced_accuracy_score(labels, predictions)),
        macro_precision=float(precision),
        macro_recall=float(recall),
        macro_f1=float(f1),
        per_class=per_class,
        confusion_matrix=tuple(tuple(int(value) for value in row) for row in matrix),
    )
