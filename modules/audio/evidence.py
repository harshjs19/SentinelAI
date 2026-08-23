import numpy as np
from numpy.typing import NDArray


def calibration_threshold(
    scores: NDArray[np.float64],
    percentile: float,
) -> float:
    if scores.size < 2 or not np.isfinite(scores).all():
        raise ValueError("Normal calibration scores must contain at least two finite values")
    if not 0 < percentile < 1:
        raise ValueError("Threshold percentile must be between 0 and 1")
    return float(np.quantile(scores, percentile, method="linear"))


def bounded_evidence(
    anomaly_score: float,
    threshold: float,
    normal_calibration_scores: NDArray[np.float64],
) -> float:
    sorted_scores = np.sort(np.asarray(normal_calibration_scores, dtype=np.float64))
    if sorted_scores.size < 2 or not np.isfinite(sorted_scores).all():
        raise ValueError("Normal calibration scores must contain at least two finite values")
    if not np.isfinite(anomaly_score) or not np.isfinite(threshold):
        raise ValueError("Anomaly score and threshold must be finite")

    percentiles = np.linspace(0.0, 1.0, sorted_scores.size)
    score_position = float(np.interp(anomaly_score, sorted_scores, percentiles))
    threshold_position = float(np.interp(threshold, sorted_scores, percentiles))
    if anomaly_score > threshold:
        denominator = 1.0 - threshold_position
        evidence = 1.0 if denominator <= 0 else (score_position - threshold_position) / denominator
    else:
        evidence = (
            1.0
            if threshold_position <= 0
            else (threshold_position - score_position) / threshold_position
        )
    return float(np.clip(evidence, 0.0, 1.0))
