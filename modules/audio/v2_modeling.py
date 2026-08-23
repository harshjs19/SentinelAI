import numpy as np
from numpy.typing import NDArray
from sklearn.covariance import LedoitWolf
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from modules.audio.config import AudioV2TrainingConfig


class CosineKNNDetector:
    def __init__(self, neighbors: int) -> None:
        if neighbors < 1:
            raise ValueError("kNN neighbors must be positive")
        self.neighbors = neighbors
        self.reference_embeddings: NDArray[np.float64] | None = None

    def fit(self, embeddings: NDArray[np.float64]) -> "CosineKNNDetector":
        _validate_fit_matrix(embeddings)
        if len(embeddings) < self.neighbors:
            raise ValueError("kNN requires at least as many normal embeddings as neighbors")
        self.reference_embeddings = _l2_normalize(embeddings)
        return self

    def anomaly_scores(self, embeddings: NDArray[np.float64]) -> NDArray[np.float64]:
        if self.reference_embeddings is None:
            raise ValueError("kNN detector has not been fitted")
        normalized = _l2_normalize(embeddings)
        distances = 1.0 - normalized @ self.reference_embeddings.T
        nearest = np.partition(distances, self.neighbors - 1, axis=1)[:, : self.neighbors]
        return np.mean(nearest, axis=1, dtype=np.float64)


class ShrinkageMahalanobisDetector:
    def __init__(self, pca_components: int, random_seed: int) -> None:
        if pca_components < 1:
            raise ValueError("Mahalanobis PCA components must be positive")
        self.pca_components = pca_components
        self.random_seed = random_seed
        self.scaler = StandardScaler()
        self.pca: PCA | None = None
        self.covariance = LedoitWolf(assume_centered=False)

    def fit(
        self,
        embeddings: NDArray[np.float64],
    ) -> "ShrinkageMahalanobisDetector":
        _validate_fit_matrix(embeddings)
        scaled = self.scaler.fit_transform(embeddings)
        components = min(self.pca_components, len(embeddings) - 1, embeddings.shape[1])
        self.pca = PCA(
            n_components=components,
            svd_solver="randomized",
            random_state=self.random_seed,
        )
        reduced = self.pca.fit_transform(scaled)
        self.covariance.fit(reduced)
        return self

    def anomaly_scores(self, embeddings: NDArray[np.float64]) -> NDArray[np.float64]:
        if self.pca is None:
            raise ValueError("Mahalanobis detector has not been fitted")
        reduced = self.pca.transform(self.scaler.transform(embeddings))
        squared_distances = self.covariance.mahalanobis(reduced)
        return np.sqrt(np.maximum(squared_distances, 0.0))


type AudioV2Detector = CosineKNNDetector | ShrinkageMahalanobisDetector


def build_v2_candidates(config: AudioV2TrainingConfig) -> dict[str, AudioV2Detector]:
    return {
        "cosine_knn": CosineKNNDetector(config.knn_neighbors),
        "shrinkage_mahalanobis": ShrinkageMahalanobisDetector(
            config.mahalanobis_pca_components,
            config.random_seed,
        ),
    }


def v2_model_parameters(name: str, config: AudioV2TrainingConfig) -> dict[str, object]:
    if name == "cosine_knn":
        return {
            "distance": "cosine",
            "neighbors": config.knn_neighbors,
            "aggregation": "mean_k_nearest_distances",
            "reference_normalization": "L2",
        }
    if name == "shrinkage_mahalanobis":
        return {
            "scaler": "StandardScaler",
            "pca_components_rule": (
                "min(configured_128, detector_fit_count_minus_1, embedding_dimension)"
            ),
            "pca_components_cap": config.mahalanobis_pca_components,
            "pca_solver": "randomized",
            "random_state": config.random_seed,
            "covariance": "LedoitWolf",
        }
    raise ValueError(f"Unknown Audio V2 detector: {name}")


def _validate_fit_matrix(embeddings: NDArray[np.float64]) -> None:
    if embeddings.ndim != 2 or len(embeddings) < 2:
        raise ValueError("Detector fitting requires a two-dimensional embedding matrix")
    if not np.isfinite(embeddings).all():
        raise ValueError("Detector embeddings must be finite")


def _l2_normalize(embeddings: NDArray[np.float64]) -> NDArray[np.float64]:
    if embeddings.ndim != 2 or not np.isfinite(embeddings).all():
        raise ValueError("kNN embeddings must be a finite two-dimensional matrix")
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    if np.any(norms <= 0):
        raise ValueError("kNN embeddings must have non-zero L2 norm")
    return embeddings / norms
