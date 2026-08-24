from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)


def classification_metrics(
    y_true: Sequence[str] | NDArray[np.str_],
    probabilities: NDArray[np.float64],
    labels: Sequence[str],
) -> dict[str, object]:
    label_tuple = tuple(labels)
    _validate_probabilities(probabilities, len(y_true), len(label_tuple))
    predictions = np.asarray(label_tuple)[np.argmax(probabilities, axis=1)]
    precision, recall, per_class_f1, support = precision_recall_fscore_support(
        y_true,
        predictions,
        labels=label_tuple,
        zero_division=0,
    )
    return {
        "accuracy": float(accuracy_score(y_true, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predictions)),
        "macro_precision": float(np.mean(precision)),
        "macro_recall": float(np.mean(recall)),
        "macro_f1": float(f1_score(y_true, predictions, labels=label_tuple, average="macro")),
        "weighted_f1": float(f1_score(y_true, predictions, labels=label_tuple, average="weighted")),
        "per_class": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(per_class_f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(label_tuple)
        },
        "confusion_matrix": confusion_matrix(y_true, predictions, labels=label_tuple).tolist(),
        "labels": list(label_tuple),
    }


def experiment_level_metrics(
    y_true: Sequence[str] | NDArray[np.str_],
    probabilities: NDArray[np.float64],
    experiment_ids: Sequence[str] | NDArray[np.str_],
    labels: Sequence[str],
) -> dict[str, object]:
    if len(y_true) != len(experiment_ids):
        raise ValueError("Experiment identities must align with Thermal frames")
    label_tuple = tuple(labels)
    _validate_probabilities(probabilities, len(y_true), len(label_tuple))
    rows: list[dict[str, object]] = []
    true_experiments: list[str] = []
    predicted_experiments: list[str] = []
    experiment_array = np.asarray(experiment_ids)
    truth_array = np.asarray(y_true)
    for experiment_id in sorted(set(experiment_ids)):
        mask = experiment_array == experiment_id
        truths = np.unique(truth_array[mask])
        if len(truths) != 1:
            raise ValueError("A Thermal experiment must contain exactly one condition label")
        mean_probabilities = probabilities[mask].mean(axis=0)
        predicted_index = int(np.argmax(mean_probabilities))
        true_label = str(truths[0])
        predicted_label = label_tuple[predicted_index]
        order = np.argsort(mean_probabilities)[::-1]
        rows.append(
            {
                "experiment_id": experiment_id,
                "true_condition": true_label,
                "predicted_condition": predicted_label,
                "predicted_probability": float(mean_probabilities[predicted_index]),
                "top_2": [
                    {
                        "condition": label_tuple[int(index)],
                        "mean_probability": float(mean_probabilities[index]),
                    }
                    for index in order[:2]
                ],
                "mean_probabilities": {
                    label: float(mean_probabilities[index])
                    for index, label in enumerate(label_tuple)
                },
                "frame_count": int(mask.sum()),
            }
        )
        true_experiments.append(true_label)
        predicted_experiments.append(predicted_label)
    return {
        "experiment_count": len(rows),
        "accuracy": float(accuracy_score(true_experiments, predicted_experiments)),
        "macro_f1": float(
            f1_score(
                true_experiments,
                predicted_experiments,
                labels=label_tuple,
                average="macro",
            )
        ),
        "experiments": rows,
    }


def aligned_probabilities(
    model: object, features: NDArray[np.float64], labels: Sequence[str]
) -> NDArray[np.float64]:
    probabilities = np.asarray(model.predict_proba(features), dtype=np.float64)  # type: ignore[attr-defined]
    classes = tuple(str(label) for label in model.classes_)  # type: ignore[attr-defined]
    label_tuple = tuple(labels)
    if set(classes) != set(label_tuple):
        raise ValueError("Thermal classifier classes do not match the canonical labels")
    indices = [classes.index(label) for label in label_tuple]
    aligned = probabilities[:, indices]
    _validate_probabilities(aligned, len(features), len(label_tuple))
    return aligned


def _validate_probabilities(
    probabilities: NDArray[np.float64],
    expected_rows: int,
    expected_columns: int,
) -> None:
    if probabilities.shape != (expected_rows, expected_columns):
        raise ValueError("Thermal class probabilities have an invalid shape")
    if (
        not np.isfinite(probabilities).all()
        or np.any(probabilities < 0)
        or np.any(probabilities > 1)
    ):
        raise ValueError("Thermal class probabilities must be finite values in [0, 1]")
    if not np.allclose(probabilities.sum(axis=1), 1.0):
        raise ValueError("Thermal class probabilities must sum to one")
