import numpy as np
from numpy.typing import NDArray
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from modules.audio.config import AudioTrainingConfig


class PCAReconstructionDetector:
    def __init__(self, variance_retained: float) -> None:
        self.variance_retained = variance_retained
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=variance_retained, svd_solver="full")

    def fit(self, features: NDArray[np.float64]) -> "PCAReconstructionDetector":
        scaled = self.scaler.fit_transform(features)
        self.pca.fit(scaled)
        return self

    def anomaly_scores(self, features: NDArray[np.float64]) -> NDArray[np.float64]:
        scaled = self.scaler.transform(features)
        reconstructed = self.pca.inverse_transform(self.pca.transform(scaled))
        return np.mean(np.square(scaled - reconstructed), axis=1)


class IsolationForestDetector:
    def __init__(self, estimators: int, random_seed: int) -> None:
        self.estimators = estimators
        self.random_seed = random_seed
        self.scaler = StandardScaler()
        self.forest = IsolationForest(
            n_estimators=estimators,
            contamination="auto",
            random_state=random_seed,
            n_jobs=-1,
        )

    def fit(self, features: NDArray[np.float64]) -> "IsolationForestDetector":
        scaled = self.scaler.fit_transform(features)
        self.forest.fit(scaled)
        return self

    def anomaly_scores(self, features: NDArray[np.float64]) -> NDArray[np.float64]:
        scaled = self.scaler.transform(features)
        return -self.forest.score_samples(scaled)


type AudioDetector = PCAReconstructionDetector | IsolationForestDetector


def build_candidates(config: AudioTrainingConfig) -> dict[str, AudioDetector]:
    return {
        "pca_reconstruction": PCAReconstructionDetector(config.pca_variance_retained),
        "isolation_forest": IsolationForestDetector(
            config.isolation_forest_estimators,
            config.random_seed,
        ),
    }


def model_parameters(name: str, config: AudioTrainingConfig) -> dict[str, object]:
    if name == "pca_reconstruction":
        return {
            "variance_retained": config.pca_variance_retained,
            "svd_solver": "full",
            "scaler": "StandardScaler",
        }
    if name == "isolation_forest":
        return {
            "n_estimators": config.isolation_forest_estimators,
            "contamination": "auto",
            "random_state": config.random_seed,
            "scaler": "StandardScaler",
        }
    raise ValueError(f"Unknown audio detector: {name}")
