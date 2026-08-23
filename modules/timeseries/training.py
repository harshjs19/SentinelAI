import json
from dataclasses import dataclass

import pandas as pd
from sklearn.pipeline import Pipeline

from ai_core.evaluation import ClassificationEvaluation
from modules.timeseries.artifact import (
    ArtifactMetadata,
    TimeseriesModelArtifact,
    load_artifact,
    save_artifact,
)
from modules.timeseries.config import (
    DATASET_REVISION,
    DATASET_SOURCE,
    FEATURE_NAMES,
    TimeseriesTrainingConfig,
)
from modules.timeseries.data import TimeseriesDataset, load_bently_dataset
from modules.timeseries.modeling import build_candidates, evaluate_classifier, model_parameters
from modules.timeseries.split import TimeseriesSplit, chronological_session_split


@dataclass(frozen=True)
class TrainingOutcome:
    selected_model: str
    validation_results: dict[str, ClassificationEvaluation]
    test_result: ClassificationEvaluation
    artifact_path: str
    evaluation_path: str


def _split_dataset(dataset: TimeseriesDataset, config: TimeseriesTrainingConfig) -> TimeseriesSplit:
    return chronological_session_split(
        dataset.windows,
        train_fraction=config.train_fraction,
        validation_fraction=config.validation_fraction,
        purge_windows=config.purge_windows,
    )


def _features_and_labels(
    frame: pd.DataFrame,
    feature_names: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.Series]:
    return frame.loc[:, feature_names], frame["label"]


def _partition_summary(split: TimeseriesSplit) -> dict[str, object]:
    return {
        name: {
            "windows": len(frame),
            "per_class": {
                label: int(count)
                for label, count in frame["label"].value_counts().sort_index().items()
            },
        }
        for name, frame in (
            ("train", split.train),
            ("validation", split.validation),
            ("test", split.test),
        )
    }


def train_timeseries(config: TimeseriesTrainingConfig) -> TrainingOutcome:
    dataset = load_bently_dataset(config.dataset_root)
    split = _split_dataset(dataset, config)
    class_names = tuple(sorted(dataset.windows["label"].unique()))
    train_features, train_labels = _features_and_labels(split.train, FEATURE_NAMES)
    validation_features, validation_labels = _features_and_labels(split.validation, FEATURE_NAMES)

    candidates = build_candidates(config)
    validation_results: dict[str, ClassificationEvaluation] = {}
    for name, pipeline in candidates.items():
        pipeline.fit(train_features, train_labels)
        validation_results[name] = evaluate_classifier(
            pipeline,
            validation_features,
            validation_labels,
            class_names,
        )

    selected_model = max(
        validation_results,
        key=lambda name: validation_results[name].macro_f1,
    )
    final_training = pd.concat([split.train, split.validation], ignore_index=True)
    final_features, final_labels = _features_and_labels(final_training, FEATURE_NAMES)
    selected_pipeline: Pipeline = build_candidates(config)[selected_model]
    selected_pipeline.fit(final_features, final_labels)

    test_features, test_labels = _features_and_labels(split.test, FEATURE_NAMES)
    test_result = evaluate_classifier(
        selected_pipeline,
        test_features,
        test_labels,
        class_names,
    )

    metadata = ArtifactMetadata(
        format_version=2,
        dataset_source=DATASET_SOURCE,
        dataset_revision=DATASET_REVISION,
        split_strategy=split.strategy,
        train_fraction=config.train_fraction,
        validation_fraction=config.validation_fraction,
        purge_windows=config.purge_windows,
        random_seed=config.random_seed,
        feature_names=FEATURE_NAMES,
        labels=class_names,
        selected_model=selected_model,
        selection_metric="validation_macro_f1",
        model_parameters=model_parameters(selected_model, config),
        validation_macro_f1=validation_results[selected_model].macro_f1,
        test_macro_f1=test_result.macro_f1,
    )
    save_artifact(
        TimeseriesModelArtifact(pipeline=selected_pipeline, metadata=metadata),
        config.artifact_path,
    )
    metadata_path = config.artifact_path.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata.to_dict(), indent=2) + "\n", encoding="utf-8")

    results = {
        "dataset": {
            "source": DATASET_SOURCE,
            "revision": DATASET_REVISION,
            "raw_rows": dataset.raw_rows,
            "dropped_rows_without_timestamp": dataset.dropped_timestamp_rows,
            "measurement_windows": len(dataset.windows),
        },
        "features": list(FEATURE_NAMES),
        "excluded_fields": ["timestamp", "status", "volts", "channel_2_metrics"],
        "split": {
            "strategy": split.strategy,
            "train_fraction": config.train_fraction,
            "validation_fraction": config.validation_fraction,
            "purge_windows": config.purge_windows,
            "random_seed": config.random_seed,
            "partitions": _partition_summary(split),
        },
        "final_fit": {
            "partitions": ["train", "validation"],
            "windows": len(final_training),
        },
        "selection_metric": "validation_macro_f1",
        "validation": {name: result.to_dict() for name, result in validation_results.items()},
        "selected_model": selected_model,
        "selected_model_parameters": model_parameters(selected_model, config),
        "test": test_result.to_dict(),
        "artifact": str(config.artifact_path),
    }
    config.evaluation_path.parent.mkdir(parents=True, exist_ok=True)
    config.evaluation_path.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return TrainingOutcome(
        selected_model=selected_model,
        validation_results=validation_results,
        test_result=test_result,
        artifact_path=str(config.artifact_path),
        evaluation_path=str(config.evaluation_path),
    )


def evaluate_saved_artifact(
    config: TimeseriesTrainingConfig,
) -> ClassificationEvaluation:
    artifact = load_artifact(config.artifact_path)
    dataset = load_bently_dataset(config.dataset_root)
    split = chronological_session_split(
        dataset.windows,
        train_fraction=artifact.metadata.train_fraction,
        validation_fraction=artifact.metadata.validation_fraction,
        purge_windows=artifact.metadata.purge_windows,
    )
    test_features, test_labels = _features_and_labels(split.test, artifact.metadata.feature_names)
    return evaluate_classifier(
        artifact.pipeline,
        test_features,
        test_labels,
        artifact.metadata.labels,
    )
