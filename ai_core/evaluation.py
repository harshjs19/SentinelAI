from dataclasses import dataclass


@dataclass(frozen=True)
class ClassificationEvaluation:
    labels: tuple[str, ...]
    accuracy: float
    balanced_accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    per_class: dict[str, dict[str, float]]
    confusion_matrix: tuple[tuple[int, ...], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "labels": list(self.labels),
            "accuracy": self.accuracy,
            "balanced_accuracy": self.balanced_accuracy,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "per_class": self.per_class,
            "confusion_matrix": [list(row) for row in self.confusion_matrix],
        }
