from dataclasses import asdict, dataclass

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


@dataclass(frozen=True)
class VisionImageEvaluation:
    roc_auc: float
    partial_auc_max_fpr_0_1: float
    average_precision: float
    threshold: float
    precision: float
    recall: float
    f1: float
    balanced_accuracy: float
    confusion_matrix: tuple[tuple[int, int], tuple[int, int]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class VisionPixelEvaluation:
    roc_auc: float
    average_precision: float
    threshold: float
    intersection_over_union: float
    dice: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def evaluate_image_scores(
    labels: NDArray[np.int64],
    scores: NDArray[np.float64],
    threshold: float,
) -> VisionImageEvaluation:
    _validate_binary_scores(labels, scores)
    predictions = (scores > threshold).astype(np.int64)
    matrix = confusion_matrix(labels, predictions, labels=[0, 1])
    return VisionImageEvaluation(
        roc_auc=float(roc_auc_score(labels, scores)),
        partial_auc_max_fpr_0_1=float(roc_auc_score(labels, scores, max_fpr=0.1)),
        average_precision=float(average_precision_score(labels, scores)),
        threshold=threshold,
        precision=float(precision_score(labels, predictions, zero_division=0)),
        recall=float(recall_score(labels, predictions, zero_division=0)),
        f1=float(f1_score(labels, predictions, zero_division=0)),
        balanced_accuracy=float(balanced_accuracy_score(labels, predictions)),
        confusion_matrix=tuple(tuple(int(value) for value in row) for row in matrix),
    )


def evaluate_pixel_scores(
    masks: NDArray[np.uint8],
    anomaly_maps: NDArray[np.float64],
    threshold: float,
) -> VisionPixelEvaluation:
    if masks.shape != anomaly_maps.shape or masks.ndim != 3:
        raise ValueError("Vision masks and anomaly maps must have matching image stacks")
    labels = masks.reshape(-1).astype(np.int64, copy=False)
    scores = anomaly_maps.reshape(-1)
    _validate_binary_scores(labels, scores)
    predicted = scores > threshold
    actual = labels == 1
    intersection = int(np.count_nonzero(predicted & actual))
    union = int(np.count_nonzero(predicted | actual))
    predicted_count = int(np.count_nonzero(predicted))
    actual_count = int(np.count_nonzero(actual))
    return VisionPixelEvaluation(
        roc_auc=float(roc_auc_score(labels, scores)),
        average_precision=float(average_precision_score(labels, scores)),
        threshold=threshold,
        intersection_over_union=intersection / union if union else 1.0,
        dice=(2 * intersection / (predicted_count + actual_count))
        if predicted_count + actual_count
        else 1.0,
    )


def score_summary(scores: NDArray[np.float64]) -> dict[str, float]:
    if scores.size < 2 or not np.isfinite(scores).all():
        raise ValueError("Vision calibration scores must contain at least two finite values")
    return {
        "minimum": float(np.min(scores)),
        "median": float(np.median(scores)),
        "p90": float(np.quantile(scores, 0.90)),
        "p95": float(np.quantile(scores, 0.95)),
        "p99": float(np.quantile(scores, 0.99)),
        "maximum": float(np.max(scores)),
    }


def _validate_binary_scores(
    labels: NDArray[np.int64],
    scores: NDArray[np.float64],
) -> None:
    if labels.ndim != 1 or scores.ndim != 1 or labels.shape != scores.shape:
        raise ValueError("Vision labels and scores must be aligned vectors")
    if set(np.unique(labels)) != {0, 1}:
        raise ValueError("Vision evaluation requires both binary classes")
    if not np.isfinite(scores).all():
        raise ValueError("Vision evaluation scores must be finite")
