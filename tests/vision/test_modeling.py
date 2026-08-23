import numpy as np
import pytest

from modules.audio.evidence import bounded_evidence, calibration_threshold
from modules.vision.modeling import GlobalMahalanobisDetector, PatchNearestNeighborDetector


def normal_patches() -> np.ndarray:
    return np.asarray(
        [
            [[[1.0, 0.0], [0.9, 0.1]], [[1.0, 0.0], [0.8, 0.2]]],
            [[[0.9, 0.1], [1.0, 0.0]], [[0.8, 0.2], [0.9, 0.1]]],
        ],
        dtype=np.float64,
    )


def test_patch_detector_is_deterministic_and_bounds_memory() -> None:
    first = PatchNearestNeighborDetector(max_bank_size=3, random_seed=42).fit(normal_patches())
    second = PatchNearestNeighborDetector(max_bank_size=3, random_seed=42).fit(normal_patches())

    assert first.bank_size == 3
    assert np.array_equal(first.memory_bank, second.memory_bank)


def test_patch_detector_scores_spatial_anomaly() -> None:
    detector = PatchNearestNeighborDetector(max_bank_size=8).fit(normal_patches())
    query = normal_patches()[:1].copy()
    query[0, 1, 1] = [0.0, 1.0]

    anomaly_map = detector.patch_scores(query)

    assert anomaly_map.shape == (1, 2, 2)
    assert anomaly_map[0, 1, 1] > anomaly_map[0, 0, 0]
    assert detector.anomaly_scores(query).shape == (1,)


def test_patch_detector_rejects_nonfinite_features() -> None:
    patches = normal_patches()
    patches[0, 0, 0, 0] = np.nan

    with pytest.raises(ValueError, match="finite"):
        PatchNearestNeighborDetector().fit(patches)


def test_global_mahalanobis_produces_finite_deterministic_scores() -> None:
    normal = np.asarray([[0.0, 0.0], [0.1, -0.1], [-0.1, 0.1], [0.05, 0.0]])
    queries = np.asarray([[0.0, 0.0], [3.0, 3.0]])
    detector = GlobalMahalanobisDetector().fit(normal)

    first = detector.anomaly_scores(queries)
    second = detector.anomaly_scores(queries)

    assert np.array_equal(first, second)
    assert np.isfinite(first).all()
    assert first[1] > first[0]


def test_threshold_and_bounded_evidence_cover_both_sides() -> None:
    calibration = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    threshold = calibration_threshold(calibration, 0.75)

    healthy = bounded_evidence(0.1, threshold, calibration)
    anomaly = bounded_evidence(0.5, threshold, calibration)

    assert 0 <= healthy <= 1
    assert 0 <= anomaly <= 1
