from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
from sklearn.pipeline import Pipeline


@dataclass(frozen=True)
class ArtifactMetadata:
    format_version: int
    dataset_source: str
    dataset_revision: str
    split_strategy: str
    train_fraction: float
    validation_fraction: float
    purge_windows: int
    random_seed: int
    feature_names: tuple[str, ...]
    labels: tuple[str, ...]
    selected_model: str
    selection_metric: str
    model_parameters: dict[str, object]
    validation_macro_f1: float
    test_macro_f1: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class TimeseriesModelArtifact:
    pipeline: Pipeline
    metadata: ArtifactMetadata


def save_artifact(artifact: TimeseriesModelArtifact, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)


def load_artifact(path: Path) -> TimeseriesModelArtifact:
    artifact = joblib.load(path)
    if not isinstance(artifact, TimeseriesModelArtifact):
        raise ValueError(f"Unsupported time-series artifact: {path}")
    if artifact.metadata.format_version != 2:
        raise ValueError(f"Unsupported artifact format: {artifact.metadata.format_version}")
    return artifact
