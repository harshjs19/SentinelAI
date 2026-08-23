import numpy as np

from modules.audio.config import AudioV2TrainingConfig
from modules.audio.v2_modeling import build_v2_candidates


def test_v2_detectors_fit_normal_embeddings_and_score_anomalies() -> None:
    random = np.random.default_rng(42)
    normal = random.normal(0.0, 0.25, size=(80, 8))
    anomalies = random.normal(4.0, 0.25, size=(5, 8))
    config = AudioV2TrainingConfig(mahalanobis_pca_components=4)

    for detector in build_v2_candidates(config).values():
        detector.fit(normal)
        normal_scores = detector.anomaly_scores(normal[:5])
        anomaly_scores = detector.anomaly_scores(anomalies)

        assert normal_scores.shape == (5,)
        assert anomaly_scores.shape == (5,)
        assert np.isfinite(normal_scores).all()
        assert np.isfinite(anomaly_scores).all()
        assert float(np.mean(anomaly_scores)) > float(np.mean(normal_scores))


def test_cosine_knn_uses_configured_neighbor_count() -> None:
    detector = build_v2_candidates(AudioV2TrainingConfig(knn_neighbors=3))["cosine_knn"]
    detector.fit(np.eye(4, dtype=np.float64))

    scores = detector.anomaly_scores(np.asarray([[1.0, 0.0, 0.0, 0.0]]))

    assert scores.shape == (1,)
    assert scores[0] == 2.0 / 3.0
