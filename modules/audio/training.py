import json
from collections import Counter
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from modules.audio.artifact import (
    AUDIO_ARTIFACT_FORMAT_VERSION,
    AudioArtifactMetadata,
    AudioModelArtifact,
    load_audio_artifact,
    save_audio_artifact,
)
from modules.audio.config import (
    DATASET_ARCHIVE,
    DATASET_CHECKSUM,
    DATASET_DOI,
    DATASET_LICENSE,
    DATASET_SOURCE,
    SUPPORTED_ASSET_TYPES,
    AudioFeatureConfig,
    AudioTrainingConfig,
)
from modules.audio.data import (
    AudioClip,
    discover_bearing_clips,
    labeled_test_clips,
    load_wav,
    normal_training_clips,
    split_normal_calibration,
)
from modules.audio.evaluation import AudioEvaluation, evaluate_audio_scores
from modules.audio.evidence import calibration_threshold
from modules.audio.features import (
    extract_audio_features,
    feature_config_metadata,
    feature_names,
)
from modules.audio.modeling import build_candidates, model_parameters

SELECTION_METRIC = "harmonic_mean(source_roc_auc,target_roc_auc,partial_auc_max_fpr_0_1)"


@dataclass(frozen=True)
class AudioTrainingOutcome:
    selected_detector: str
    validation_results: dict[str, AudioEvaluation]
    test_result: AudioEvaluation
    artifact_path: str
    evaluation_path: str


def train_audio(config: AudioTrainingConfig) -> AudioTrainingOutcome:
    clips = discover_bearing_clips(config.dataset_root)
    available_sections = {clip.section for clip in clips}
    if not {"00", "01", "02"}.issubset(available_sections):
        raise ValueError("MIMII DG bearing sections 00, 01, and 02 are required")

    cache: dict[object, NDArray[np.float64]] = {}

    def feature_matrix(selected_clips: tuple[AudioClip, ...]) -> NDArray[np.float64]:
        rows = []
        for clip in selected_clips:
            if clip.path not in cache:
                cache[clip.path] = extract_audio_features(load_wav(clip.path), config.feature)
            rows.append(cache[clip.path])
        return np.vstack(rows)

    section_00_normal = normal_training_clips(clips, {"00"})
    candidate_fit_clips, candidate_calibration_clips = split_normal_calibration(
        section_00_normal,
        config.calibration_stride,
    )
    candidate_fit_features = feature_matrix(candidate_fit_clips)
    candidate_calibration_features = feature_matrix(candidate_calibration_clips)
    validation_clips = labeled_test_clips(clips, "01")
    validation_features = feature_matrix(validation_clips)
    validation_labels, validation_domains = _labels_and_domains(validation_clips)

    validation_results: dict[str, AudioEvaluation] = {}
    for name, detector in build_candidates(config).items():
        detector.fit(candidate_fit_features)
        calibration_scores = detector.anomaly_scores(candidate_calibration_features)
        threshold = calibration_threshold(calibration_scores, config.threshold_percentile)
        validation_results[name] = evaluate_audio_scores(
            validation_labels,
            validation_domains,
            detector.anomaly_scores(validation_features),
            threshold,
        )

    selected_detector = max(
        validation_results,
        key=lambda name: validation_results[name].selection_score,
    )

    final_normal = normal_training_clips(clips, {"00", "01"})
    final_fit_clips, final_calibration_clips = split_normal_calibration(
        final_normal,
        config.calibration_stride,
    )
    final_detector = build_candidates(config)[selected_detector]
    final_detector.fit(feature_matrix(final_fit_clips))
    final_calibration_scores = final_detector.anomaly_scores(
        feature_matrix(final_calibration_clips)
    )
    final_threshold = calibration_threshold(
        final_calibration_scores,
        config.threshold_percentile,
    )

    test_clips = labeled_test_clips(clips, "02")
    test_labels, test_domains = _labels_and_domains(test_clips)
    test_result = evaluate_audio_scores(
        test_labels,
        test_domains,
        final_detector.anomaly_scores(feature_matrix(test_clips)),
        final_threshold,
    )

    selected_validation = validation_results[selected_detector]
    metadata = AudioArtifactMetadata(
        format_version=AUDIO_ARTIFACT_FORMAT_VERSION,
        dataset_source=DATASET_SOURCE,
        dataset_doi=DATASET_DOI,
        dataset_license=DATASET_LICENSE,
        dataset_archive=DATASET_ARCHIVE,
        dataset_checksum=DATASET_CHECKSUM,
        machine_subset="bearing",
        supported_asset_types=SUPPORTED_ASSET_TYPES,
        audio_sample_rate=config.feature.sample_rate,
        audio_channels=1,
        clip_duration_seconds=10.0,
        feature_config=feature_config_metadata(config.feature),
        feature_names=feature_names(config.feature),
        selected_detector=selected_detector,
        model_parameters=model_parameters(selected_detector, config),
        training_sections=("00", "01"),
        validation_section="01",
        test_section="02",
        selection_metric=SELECTION_METRIC,
        threshold_policy=(
            f"linear {config.threshold_percentile:.1%} percentile of held-out normal scores"
        ),
        threshold_percentile=config.threshold_percentile,
        threshold=final_threshold,
        calibration_count=len(final_calibration_scores),
        calibration_score_summary=_score_summary(final_calibration_scores),
        validation_metrics=selected_validation.to_dict(),
        test_metrics=test_result.to_dict(),
    )
    artifact = AudioModelArtifact(
        detector=final_detector,
        normal_calibration_scores=tuple(float(score) for score in final_calibration_scores),
        metadata=metadata,
    )
    save_audio_artifact(artifact, config.artifact_path)
    metadata_path = config.artifact_path.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata.to_dict(), indent=2) + "\n", encoding="utf-8")

    results = {
        "dataset": {
            "source": DATASET_SOURCE,
            "doi": DATASET_DOI,
            "license": DATASET_LICENSE,
            "archive": DATASET_ARCHIVE,
            "checksum": DATASET_CHECKSUM,
            "machine_subset": "bearing",
            "total_clips": len(clips),
            "counts": _clip_counts(clips),
            "audio": {
                "sample_rate": config.feature.sample_rate,
                "channels": 1,
                "duration_seconds": 10.0,
            },
        },
        "features": {
            "config": feature_config_metadata(config.feature),
            "names": list(feature_names(config.feature)),
            "dimension": len(feature_names(config.feature)),
            "excluded_metadata": [
                "filename",
                "filesystem_path",
                "section",
                "domain",
                "split",
                "normal_anomaly_label",
                "operating_attributes",
            ],
        },
        "protocol": {
            "candidate_training_section": "00",
            "validation_section": "01",
            "final_training_sections": ["00", "01"],
            "held_out_test_section": "02",
            "normal_only_training": True,
            "calibration_stride": config.calibration_stride,
            "candidate_fit_clips": len(candidate_fit_clips),
            "candidate_calibration_clips": len(candidate_calibration_clips),
            "final_fit_clips": len(final_fit_clips),
            "final_calibration_clips": len(final_calibration_clips),
        },
        "candidates": {
            name: {
                "parameters": model_parameters(name, config),
                "validation": result.to_dict(),
            }
            for name, result in validation_results.items()
        },
        "selection_metric": SELECTION_METRIC,
        "selected_detector": selected_detector,
        "threshold": {
            "policy": metadata.threshold_policy,
            "percentile": config.threshold_percentile,
            "value": final_threshold,
            "normal_calibration_count": len(final_calibration_scores),
            "score_summary": metadata.calibration_score_summary,
        },
        "test": test_result.to_dict(),
        "artifact": str(config.artifact_path),
        "known_limitations": [
            "bearing subset only",
            "classical log-mel summary baseline",
            "raw empirical evidence is not a calibrated probability",
            "held-out section evaluation is not an official DCASE score",
            "no multimodal fusion",
        ],
    }
    config.evaluation_path.parent.mkdir(parents=True, exist_ok=True)
    config.evaluation_path.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return AudioTrainingOutcome(
        selected_detector=selected_detector,
        validation_results=validation_results,
        test_result=test_result,
        artifact_path=str(config.artifact_path),
        evaluation_path=str(config.evaluation_path),
    )


def evaluate_saved_audio_artifact(config: AudioTrainingConfig) -> AudioEvaluation:
    artifact = load_audio_artifact(config.artifact_path)
    feature = _feature_config_from_metadata(artifact.metadata.feature_config)
    clips = labeled_test_clips(
        discover_bearing_clips(config.dataset_root),
        artifact.metadata.test_section,
    )
    features = np.vstack([extract_audio_features(load_wav(clip.path), feature) for clip in clips])
    labels, domains = _labels_and_domains(clips)
    return evaluate_audio_scores(
        labels,
        domains,
        artifact.detector.anomaly_scores(features),
        artifact.metadata.threshold,
    )


def _labels_and_domains(
    clips: tuple[AudioClip, ...],
) -> tuple[NDArray[np.int64], tuple[str, ...]]:
    labels = np.asarray([int(clip.is_anomaly) for clip in clips], dtype=np.int64)
    return labels, tuple(clip.domain for clip in clips)


def _clip_counts(clips: tuple[AudioClip, ...]) -> list[dict[str, object]]:
    counts = Counter((clip.section, clip.split, clip.domain, clip.label) for clip in clips)
    return [
        {
            "section": section,
            "split": split,
            "domain": domain,
            "label": label,
            "count": count,
        }
        for (section, split, domain, label), count in sorted(counts.items())
    ]


def _score_summary(scores: NDArray[np.float64]) -> dict[str, float]:
    return {
        "minimum": float(np.min(scores)),
        "median": float(np.median(scores)),
        "p90": float(np.quantile(scores, 0.90)),
        "p95": float(np.quantile(scores, 0.95)),
        "p99": float(np.quantile(scores, 0.99)),
        "maximum": float(np.max(scores)),
    }


def _feature_config_from_metadata(metadata: dict[str, object]) -> AudioFeatureConfig:
    return AudioFeatureConfig(
        sample_rate=int(metadata["sample_rate"]),
        n_mels=int(metadata["n_mels"]),
        n_fft=int(metadata["n_fft"]),
        hop_length=int(metadata["hop_length"]),
        fmin=float(metadata["fmin"]),
        fmax=float(metadata["fmax"]),
    )
