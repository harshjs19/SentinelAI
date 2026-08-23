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
class AudioEvaluation:
    roc_auc: float
    partial_auc_max_fpr_0_1: float
    average_precision: float
    source_roc_auc: float
    target_roc_auc: float
    selection_score: float
    threshold: float
    precision: float
    recall: float
    f1: float
    balanced_accuracy: float
    confusion_matrix: tuple[tuple[int, int], tuple[int, int]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_audio_scores(
    labels: NDArray[np.int64],
    domains: tuple[str, ...],
    scores: NDArray[np.float64],
    threshold: float,
) -> AudioEvaluation:
    source_mask = np.asarray([domain == "source" for domain in domains])
    target_mask = np.asarray([domain == "target" for domain in domains])
    source_auc = float(roc_auc_score(labels[source_mask], scores[source_mask]))
    target_auc = float(roc_auc_score(labels[target_mask], scores[target_mask]))
    partial_auc = float(roc_auc_score(labels, scores, max_fpr=0.1))
    predictions = (scores > threshold).astype(np.int64)
    matrix = confusion_matrix(labels, predictions, labels=[0, 1])

    return AudioEvaluation(
        roc_auc=float(roc_auc_score(labels, scores)),
        partial_auc_max_fpr_0_1=partial_auc,
        average_precision=float(average_precision_score(labels, scores)),
        source_roc_auc=source_auc,
        target_roc_auc=target_auc,
        selection_score=harmonic_selection_score(source_auc, target_auc, partial_auc),
        threshold=threshold,
        precision=float(precision_score(labels, predictions, zero_division=0)),
        recall=float(recall_score(labels, predictions, zero_division=0)),
        f1=float(f1_score(labels, predictions, zero_division=0)),
        balanced_accuracy=float(balanced_accuracy_score(labels, predictions)),
        confusion_matrix=tuple(tuple(int(value) for value in row) for row in matrix),
    )


def harmonic_selection_score(source_auc: float, target_auc: float, partial_auc: float) -> float:
    values = (source_auc, target_auc, partial_auc)
    if any(value <= 0 for value in values):
        return 0.0
    return 3.0 / sum(1.0 / value for value in values)
