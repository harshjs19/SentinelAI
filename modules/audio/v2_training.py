import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from modules.audio.artifact import (
    AUDIO_V2_ARTIFACT_FORMAT_VERSION,
    AudioV2ArtifactMetadata,
    AudioV2ModelArtifact,
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
    AudioV2TrainingConfig,
)
from modules.audio.data import (
    AudioClip,
    discover_bearing_clips,
    labeled_test_clips,
    load_wav,
    normal_training_clips,
    split_normal_calibration,
)
from modules.audio.embedding_cache import (
    CACHE_FORMAT_VERSION,
    EmbeddingCacheMetadata,
    StaleEmbeddingCacheError,
    load_embedding_cache,
    save_embedding_cache,
)
from modules.audio.encoder import AudioEmbeddingEncoder, FrozenASTEncoder
from modules.audio.evaluation import AudioEvaluation, evaluate_audio_scores
from modules.audio.evidence import calibration_threshold
from modules.audio.v2_modeling import build_v2_candidates, v2_model_parameters

SELECTION_METRIC = "harmonic_mean(source_roc_auc,target_roc_auc,partial_auc_max_fpr_0_1)"
V1_SELECTION_REFERENCE = 0.5801603837048501


@dataclass(frozen=True)
class AudioV2TrainingOutcome:
    selected_detector: str
    validation_results: dict[str, AudioEvaluation]
    benchmark_result: AudioEvaluation
    promoted: bool
    artifact_path: str
    evaluation_path: str


@dataclass(frozen=True)
class EmbeddingLoadResult:
    embeddings: NDArray[np.float64]
    cache_hit: bool
    extraction_seconds: float


def train_audio_v2(
    config: AudioV2TrainingConfig,
    encoder: AudioEmbeddingEncoder | None = None,
) -> AudioV2TrainingOutcome:
    clips = discover_bearing_clips(config.dataset_root)
    if not {"00", "01", "02"}.issubset({clip.section for clip in clips}):
        raise ValueError("MIMII DG bearing sections 00, 01, and 02 are required")
    active_encoder = encoder or FrozenASTEncoder(config.encoder_path, config.device)
    loaded = load_or_create_embeddings(config, clips, active_encoder)
    relative_paths = _relative_paths(config, clips)
    embedding_by_path = dict(zip(relative_paths, loaded.embeddings, strict=True))

    def embedding_matrix(selected_clips: tuple[AudioClip, ...]) -> NDArray[np.float64]:
        return np.vstack(
            [embedding_by_path[_relative_path(config, clip)] for clip in selected_clips]
        )

    section_00_normal = normal_training_clips(clips, {"00"})
    candidate_fit_clips, candidate_calibration_clips = split_normal_calibration(
        section_00_normal,
        config.calibration_stride,
    )
    candidate_fit = embedding_matrix(candidate_fit_clips)
    candidate_calibration = embedding_matrix(candidate_calibration_clips)
    validation_clips = labeled_test_clips(clips, "01")
    validation = embedding_matrix(validation_clips)
    validation_labels, validation_domains = _labels_and_domains(validation_clips)

    validation_results: dict[str, AudioEvaluation] = {}
    for name, detector in build_v2_candidates(config).items():
        detector.fit(candidate_fit)
        calibration_scores = detector.anomaly_scores(candidate_calibration)
        threshold = calibration_threshold(calibration_scores, config.threshold_percentile)
        validation_results[name] = evaluate_audio_scores(
            validation_labels,
            validation_domains,
            detector.anomaly_scores(validation),
            threshold,
        )

    selected_detector = max(
        validation_results,
        key=lambda name: validation_results[name].selection_score,
    )
    selected_validation = validation_results[selected_detector]
    promoted = selected_validation.selection_score > V1_SELECTION_REFERENCE

    final_normal = normal_training_clips(clips, {"00", "01"})
    final_fit_clips, final_calibration_clips = split_normal_calibration(
        final_normal,
        config.calibration_stride,
    )
    final_detector = build_v2_candidates(config)[selected_detector]
    final_detector.fit(embedding_matrix(final_fit_clips))
    final_calibration_scores = final_detector.anomaly_scores(
        embedding_matrix(final_calibration_clips)
    )
    final_threshold = calibration_threshold(
        final_calibration_scores,
        config.threshold_percentile,
    )

    benchmark_clips = labeled_test_clips(clips, "02")
    benchmark_labels, benchmark_domains = _labels_and_domains(benchmark_clips)
    benchmark_result = evaluate_audio_scores(
        benchmark_labels,
        benchmark_domains,
        final_detector.anomaly_scores(embedding_matrix(benchmark_clips)),
        final_threshold,
    )

    metadata = AudioV2ArtifactMetadata(
        format_version=AUDIO_V2_ARTIFACT_FORMAT_VERSION,
        dataset_source=DATASET_SOURCE,
        dataset_doi=DATASET_DOI,
        dataset_license=DATASET_LICENSE,
        dataset_archive=DATASET_ARCHIVE,
        dataset_checksum=DATASET_CHECKSUM,
        machine_subset="bearing",
        supported_asset_types=SUPPORTED_ASSET_TYPES,
        audio_sample_rate=int(active_encoder.metadata.preprocessing_config["sampling_rate"]),
        audio_channels=1,
        clip_duration_seconds=10.0,
        encoder=active_encoder.metadata,
        selected_detector=selected_detector,
        model_parameters=v2_model_parameters(selected_detector, config),
        training_sections=("00", "01"),
        validation_section="01",
        benchmark_section="02",
        selection_metric=SELECTION_METRIC,
        threshold_policy=(
            f"linear {config.threshold_percentile:.1%} percentile of held-out normal scores"
        ),
        threshold_percentile=config.threshold_percentile,
        threshold=final_threshold,
        calibration_count=len(final_calibration_scores),
        calibration_score_summary=_score_summary(final_calibration_scores),
        validation_metrics=selected_validation.to_dict(),
        benchmark_metrics=benchmark_result.to_dict(),
    )
    artifact = AudioV2ModelArtifact(
        detector=final_detector,
        normal_calibration_scores=tuple(float(score) for score in final_calibration_scores),
        metadata=metadata,
    )
    _save_artifact_with_metadata(artifact, config.artifact_path)
    if promoted:
        _save_artifact_with_metadata(artifact, config.runtime_artifact_path)

    single_clip_seconds = _measure_single_clip_encoder_latency(
        active_encoder,
        benchmark_clips[0],
    )
    results = _results_document(
        config=config,
        clips=clips,
        encoder=active_encoder,
        loaded=loaded,
        candidate_fit_clips=candidate_fit_clips,
        candidate_calibration_clips=candidate_calibration_clips,
        final_fit_clips=final_fit_clips,
        final_calibration_clips=final_calibration_clips,
        validation_results=validation_results,
        selected_detector=selected_detector,
        promoted=promoted,
        final_threshold=final_threshold,
        final_calibration_scores=final_calibration_scores,
        benchmark_result=benchmark_result,
        single_clip_seconds=single_clip_seconds,
    )
    config.evaluation_path.parent.mkdir(parents=True, exist_ok=True)
    config.evaluation_path.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return AudioV2TrainingOutcome(
        selected_detector=selected_detector,
        validation_results=validation_results,
        benchmark_result=benchmark_result,
        promoted=promoted,
        artifact_path=str(config.artifact_path),
        evaluation_path=str(config.evaluation_path),
    )


def load_or_create_embeddings(
    config: AudioV2TrainingConfig,
    clips: tuple[AudioClip, ...],
    encoder: AudioEmbeddingEncoder,
) -> EmbeddingLoadResult:
    relative_paths = _relative_paths(config, clips)
    cache_metadata = EmbeddingCacheMetadata(
        format_version=CACHE_FORMAT_VERSION,
        dataset_checksum=DATASET_CHECKSUM,
        encoder=encoder.metadata,
    )
    try:
        embeddings = load_embedding_cache(
            config.embedding_cache_path,
            relative_paths,
            cache_metadata,
        )
        return EmbeddingLoadResult(embeddings, cache_hit=True, extraction_seconds=0.0)
    except StaleEmbeddingCacheError:
        pass

    started = time.perf_counter()
    rows: list[NDArray[np.float64]] = []
    batch_size = config.embedding_batch_size
    if batch_size < 1:
        raise ValueError("Embedding batch size must be positive")
    for start in range(0, len(clips), batch_size):
        batch = clips[start : start + batch_size]
        rows.append(encoder.encode_batch(tuple(load_wav(clip.path) for clip in batch)))
        completed = min(start + batch_size, len(clips))
        if completed == len(clips) or completed % 100 == 0:
            print(f"AST embeddings: {completed}/{len(clips)}", flush=True)
    embeddings = np.vstack(rows)
    extraction_seconds = time.perf_counter() - started
    save_embedding_cache(
        config.embedding_cache_path,
        relative_paths,
        embeddings,
        cache_metadata,
    )
    return EmbeddingLoadResult(embeddings, cache_hit=False, extraction_seconds=extraction_seconds)


def evaluate_saved_audio_v2_artifact(
    config: AudioV2TrainingConfig,
    encoder: AudioEmbeddingEncoder | None = None,
) -> AudioEvaluation:
    artifact = load_audio_artifact(config.artifact_path)
    if not isinstance(artifact, AudioV2ModelArtifact):
        raise ValueError("Saved audio artifact is not an Audio V2 artifact")
    clips = discover_bearing_clips(config.dataset_root)
    active_encoder = encoder or FrozenASTEncoder(
        config.encoder_path,
        config.device,
        artifact.metadata.encoder,
    )
    loaded = load_or_create_embeddings(config, clips, active_encoder)
    embedding_by_path = dict(zip(_relative_paths(config, clips), loaded.embeddings, strict=True))
    benchmark = labeled_test_clips(clips, artifact.metadata.benchmark_section)
    embeddings = np.vstack([embedding_by_path[_relative_path(config, clip)] for clip in benchmark])
    labels, domains = _labels_and_domains(benchmark)
    return evaluate_audio_scores(
        labels,
        domains,
        artifact.detector.anomaly_scores(embeddings),
        artifact.metadata.threshold,
    )


def _save_artifact_with_metadata(
    artifact: AudioV2ModelArtifact,
    path: Path,
) -> None:
    save_audio_artifact(artifact, path)
    metadata_path = path.with_suffix(".metadata.json")
    metadata_path.write_text(
        json.dumps(artifact.metadata.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _results_document(
    *,
    config: AudioV2TrainingConfig,
    clips: tuple[AudioClip, ...],
    encoder: AudioEmbeddingEncoder,
    loaded: EmbeddingLoadResult,
    candidate_fit_clips: tuple[AudioClip, ...],
    candidate_calibration_clips: tuple[AudioClip, ...],
    final_fit_clips: tuple[AudioClip, ...],
    final_calibration_clips: tuple[AudioClip, ...],
    validation_results: dict[str, AudioEvaluation],
    selected_detector: str,
    promoted: bool,
    final_threshold: float,
    final_calibration_scores: NDArray[np.float64],
    benchmark_result: AudioEvaluation,
    single_clip_seconds: float,
) -> dict[str, object]:
    baseline = json.loads(
        config.evaluation_path.with_name("audio_baseline_results.json").read_text("utf-8")
    )
    v1_test = baseline["test"]
    delta_keys = {
        "roc_auc": "roc_auc",
        "partial_auc_max_fpr_0_1": "partial_auc_max_fpr_0_1",
        "average_precision": "average_precision",
        "f1": "f1",
        "balanced_accuracy": "balanced_accuracy",
        "source_roc_auc": "source_roc_auc",
        "target_roc_auc": "target_roc_auc",
    }
    benchmark_dict = benchmark_result.to_dict()
    encoder_identity = _encoder_identity(config.encoder_path)
    return {
        "experiment": {
            "name": "SentinelAI Audio Intelligence V2",
            "hypothesis": (
                "V1's main limitation is representation quality rather than only the "
                "classical detector family"
            ),
            "normal_only_anomaly_detection": True,
        },
        "v1_reference": {
            "evaluation_file": "evaluation/audio_baseline_results.json",
            "selected_detector": baseline["selected_detector"],
            "validation": baseline["candidates"]["pca_reconstruction"]["validation"],
            "section_02": v1_test,
        },
        "dataset": {
            "source": DATASET_SOURCE,
            "doi": DATASET_DOI,
            "license": DATASET_LICENSE,
            "archive": DATASET_ARCHIVE,
            "checksum": DATASET_CHECKSUM,
            "machine_subset": "bearing",
            "total_clips": len(clips),
            "counts": _clip_counts(clips),
        },
        "encoder": {
            **encoder.metadata.to_dict(),
            "frozen": True,
            "classification_logits_used": False,
            "checkpoint_format": encoder_identity["checkpoint_format"],
            "prepared_files": encoder_identity["files"],
            "local_prepared_bytes": encoder_identity["total_prepared_bytes"],
        },
        "embedding": {
            "cache_path": str(config.embedding_cache_path),
            "cache_format_version": CACHE_FORMAT_VERSION,
            "cache_hit": loaded.cache_hit,
            "cached_clip_count": len(clips),
            "extraction_seconds": loaded.extraction_seconds,
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
        "normal_fit_calibration_protocol": {
            "candidate_training_section": "00",
            "validation_section": "01",
            "final_training_sections": ["00", "01"],
            "benchmark_section": "02",
            "benchmark_status": "locked post-baseline Section 02 benchmark",
            "calibration_stride": config.calibration_stride,
            "random_seed": config.random_seed,
            "candidate_fit_normal_count": len(candidate_fit_clips),
            "candidate_calibration_normal_count": len(candidate_calibration_clips),
            "final_fit_normal_count": len(final_fit_clips),
            "final_calibration_normal_count": len(final_calibration_clips),
            "anomalies_used_for_fitting": 0,
        },
        "candidates": {
            name: {
                "parameters": v2_model_parameters(name, config),
                "validation": result.to_dict(),
            }
            for name, result in validation_results.items()
        },
        "selection_metric": {
            "name": SELECTION_METRIC,
            "formula": "3 / (1/source_roc_auc + 1/target_roc_auc + 1/pauc_at_0_1)",
            "section": "01",
        },
        "selected_candidate": selected_detector,
        "promotion_decision": {
            "promoted": promoted,
            "basis": "Section 01 validation selection score only",
            "v1_reference_score": V1_SELECTION_REFERENCE,
            "v2_selected_score": validation_results[selected_detector].selection_score,
            "runtime_artifact": str(config.runtime_artifact_path),
        },
        "validation": validation_results[selected_detector].to_dict(),
        "section_02_benchmark": benchmark_dict,
        "delta_vs_v1": {
            output_key: float(benchmark_dict[result_key]) - float(v1_test[result_key])
            for output_key, result_key in delta_keys.items()
        },
        "threshold": {
            "policy": (
                f"linear {config.threshold_percentile:.1%} percentile of held-out normal scores"
            ),
            "percentile": config.threshold_percentile,
            "value": final_threshold,
            "normal_calibration_count": len(final_calibration_scores),
            "score_summary": _score_summary(final_calibration_scores),
        },
        "runtime": {
            "device": encoder.device,
            "single_clip_encoder_seconds": single_clip_seconds,
            "v2_artifact": str(config.artifact_path),
            "v2_artifact_bytes": config.artifact_path.stat().st_size,
            "server_side_inference": True,
        },
        "limitations": [
            "bearing reference distribution only",
            "Section 02 is post-baseline and not a pristine Audio V2 holdout",
            "frozen AST may not generalize to industrial domain shifts",
            "raw empirical evidence is not a calibrated probability",
            "Audio and time-series confidence are not cross-modally calibrated",
            "no multimodal fusion, health score, risk score, or fault diagnosis",
            "86M-parameter AST is intended for backend/server inference, not Raspberry Pi 4",
        ],
    }


def _measure_single_clip_encoder_latency(
    encoder: AudioEmbeddingEncoder,
    clip: AudioClip,
) -> float:
    started = time.perf_counter()
    encoder.encode_batch((load_wav(clip.path),))
    return time.perf_counter() - started


def _encoder_identity(encoder_path: Path) -> dict[str, object]:
    return json.loads((encoder_path / "sentinelai_encoder.json").read_text("utf-8"))


def _labels_and_domains(
    clips: tuple[AudioClip, ...],
) -> tuple[NDArray[np.int64], tuple[str, ...]]:
    return (
        np.asarray([int(clip.is_anomaly) for clip in clips], dtype=np.int64),
        tuple(clip.domain for clip in clips),
    )


def _relative_paths(
    config: AudioV2TrainingConfig,
    clips: tuple[AudioClip, ...],
) -> tuple[str, ...]:
    return tuple(_relative_path(config, clip) for clip in clips)


def _relative_path(config: AudioV2TrainingConfig, clip: AudioClip) -> str:
    return clip.path.relative_to(config.dataset_root).as_posix()


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
