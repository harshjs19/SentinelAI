import numpy as np
from numpy.typing import NDArray
from sklearn.covariance import LedoitWolf
from sklearn.preprocessing import StandardScaler


class PatchNearestNeighborDetector:
    def __init__(
        self,
        max_bank_size: int = 5_000,
        random_seed: int = 42,
        image_score_percentile: float = 0.99,
    ) -> None:
        if max_bank_size <= 0:
            raise ValueError("Patch memory-bank size must be positive")
        if not 0 < image_score_percentile <= 1:
            raise ValueError("Patch image-score percentile must be in (0, 1]")
        self.max_bank_size = max_bank_size
        self.random_seed = random_seed
        self.image_score_percentile = image_score_percentile
        self.memory_bank: NDArray[np.float32] | None = None

    def fit(self, patch_embeddings: NDArray[np.float64]) -> "PatchNearestNeighborDetector":
        patches = _flatten_patch_embeddings(patch_embeddings)
        normalized = _l2_normalize(patches).astype(np.float32, copy=False)
        if len(normalized) > self.max_bank_size:
            random = np.random.default_rng(self.random_seed)
            indices = np.sort(
                random.choice(len(normalized), size=self.max_bank_size, replace=False)
            )
            normalized = normalized[indices]
        self.memory_bank = np.ascontiguousarray(normalized)
        return self

    def patch_scores(self, patch_embeddings: NDArray[np.float64]) -> NDArray[np.float64]:
        if self.memory_bank is None:
            raise RuntimeError("Patch detector must be fitted before scoring")
        if patch_embeddings.ndim != 4:
            raise ValueError("Patch embeddings must have shape (images, height, width, features)")
        images, height, width, _ = patch_embeddings.shape
        queries = _l2_normalize(patch_embeddings.reshape(-1, patch_embeddings.shape[-1]))
        scores = np.empty(len(queries), dtype=np.float64)
        bank = self.memory_bank.astype(np.float64, copy=False)
        for start in range(0, len(queries), 1_024):
            stop = min(start + 1_024, len(queries))
            maximum_similarity = np.max(queries[start:stop] @ bank.T, axis=1)
            scores[start:stop] = np.clip(1.0 - maximum_similarity, 0.0, 2.0)
        return scores.reshape(images, height, width)

    def anomaly_scores(self, patch_embeddings: NDArray[np.float64]) -> NDArray[np.float64]:
        patch_scores = self.patch_scores(patch_embeddings).reshape(len(patch_embeddings), -1)
        return np.quantile(
            patch_scores,
            self.image_score_percentile,
            axis=1,
            method="linear",
        ).astype(np.float64, copy=False)

    @property
    def bank_size(self) -> int:
        if self.memory_bank is None:
            return 0
        return len(self.memory_bank)


class GlobalMahalanobisDetector:
    def __init__(self) -> None:
        self.scaler = StandardScaler()
        self.covariance = LedoitWolf(assume_centered=False)
        self._fitted = False

    def fit(self, embeddings: NDArray[np.float64]) -> "GlobalMahalanobisDetector":
        _validate_matrix(embeddings, "Global embeddings")
        scaled = self.scaler.fit_transform(embeddings)
        self.covariance.fit(scaled)
        self._fitted = True
        return self

    def anomaly_scores(self, embeddings: NDArray[np.float64]) -> NDArray[np.float64]:
        if not self._fitted:
            raise RuntimeError("Global detector must be fitted before scoring")
        _validate_matrix(embeddings, "Global embeddings")
        squared_distances = self.covariance.mahalanobis(self.scaler.transform(embeddings))
        return np.sqrt(np.clip(squared_distances, 0.0, None)).astype(np.float64, copy=False)


def _flatten_patch_embeddings(embeddings: NDArray[np.float64]) -> NDArray[np.float64]:
    if embeddings.ndim != 4:
        raise ValueError("Patch embeddings must have shape (images, height, width, features)")
    flattened = embeddings.reshape(-1, embeddings.shape[-1])
    _validate_matrix(flattened, "Patch embeddings")
    return flattened


def _l2_normalize(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    _validate_matrix(matrix, "Patch embeddings")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, np.finfo(np.float64).eps)


def _validate_matrix(matrix: NDArray[np.float64], name: str) -> None:
    if matrix.ndim != 2 or matrix.shape[0] < 1 or matrix.shape[1] < 1:
        raise ValueError(f"{name} must be a non-empty two-dimensional matrix")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} must contain only finite values")
