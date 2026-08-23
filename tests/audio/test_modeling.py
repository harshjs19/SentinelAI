import numpy as np

from modules.audio.config import AudioTrainingConfig
from modules.audio.evaluation import evaluate_audio_scores, harmonic_selection_score
from modules.audio.evidence import bounded_evidence, calibration_threshold
from modules.audio.modeling import build_candidates


def test_candidates_fit_normal_features_and_generate_finite_scores() -> None:
    random = np.random.default_rng(42)
    normal = random.normal(size=(80, 8))
    config = AudioTrainingConfig(isolation_forest_estimators=20)

    for detector in build_candidates(config).values():
        detector.fit(normal)
        scores = detector.anomaly_scores(normal[:5])

        assert scores.shape == (5,)
        assert np.isfinite(scores).all()


def test_threshold_and_empirical_evidence_are_bounded() -> None:
    calibration = np.linspace(0.0, 1.0, 101)
    threshold = calibration_threshold(calibration, 0.99)

    confidences = [
        bounded_evidence(score, threshold, calibration)
        for score in (-1.0, 0.5, threshold, 0.995, 2.0)
    ]

    assert threshold == 0.99
    assert all(0 <= confidence <= 1 for confidence in confidences)
    assert bounded_evidence(threshold, threshold, calibration) == 0.0
    assert bounded_evidence(2.0, threshold, calibration) == 1.0


def test_evaluation_reports_domain_and_threshold_metrics() -> None:
    labels = np.asarray([0, 1, 0, 1], dtype=np.int64)
    domains = ("source", "source", "target", "target")
    scores = np.asarray([0.1, 0.9, 0.2, 0.8])

    result = evaluate_audio_scores(labels, domains, scores, threshold=0.5)

    assert result.roc_auc == 1.0
    assert result.source_roc_auc == 1.0
    assert result.target_roc_auc == 1.0
    assert result.f1 == 1.0
    assert result.confusion_matrix == ((2, 0), (0, 2))
    assert harmonic_selection_score(1.0, 1.0, 1.0) == 1.0
