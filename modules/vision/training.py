import hashlib
import json
import time
import tracemalloc
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from modules.audio.evidence import calibration_threshold
from modules.vision.artifact import (
    VISION_ARTIFACT_FORMAT_VERSION,
    VisionArtifactMetadata,
    VisionModelArtifact,
    save_vision_artifact,
)
from modules.vision.config import (
    SUPPORTED_ASSET_TYPES,
    VISA_ARCHIVE_URL,
    VISA_LICENSE,
    VISA_SOURCE,
    VisionTrainingConfig,
)
from modules.vision.data import (
    VisionSample,
    discover_pcb1_samples,
    load_image,
    load_mask,
    split_normal_training,
)
from modules.vision.encoder import (
    FrozenResNet18Encoder,
    VisionFeatureEncoder,
    VisionFeatures,
    validate_features,
)
from modules.vision.evaluation import (
    VisionImageEvaluation,
    VisionPixelEvaluation,
    evaluate_image_scores,
    evaluate_pixel_scores,
    score_summary,
)
from modules.vision.modeling import GlobalMahalanobisDetector, PatchNearestNeighborDetector
from modules.vision.preprocessing import preprocess_image, preprocess_mask, resize_anomaly_map


@dataclass(frozen=True)
class VisionTrainingOutcome:
    global_evaluation: VisionImageEvaluation
    patch_evaluation: VisionImageEvaluation
    localization_evaluation: VisionPixelEvaluation
    artifact_path: str
    evaluation_path: str


@dataclass(frozen=True)
class CachedVisionFeatures:
    relative_paths: tuple[str, ...]
    global_embeddings: NDArray[np.float64]
    patch_embeddings: NDArray[np.float64]
    cache_hit: bool
    extraction_seconds: float


def train_vision(
    config: VisionTrainingConfig,
    encoder: VisionFeatureEncoder | None = None,
) -> VisionTrainingOutcome:
    tracemalloc.start()
    samples = discover_pcb1_samples(config.dataset_root, config.official_split_path)
    fit_samples, calibration_samples = split_normal_training(
        samples,
        config.fit_fraction,
        config.random_seed,
    )
    test_samples = tuple(sample for sample in samples if sample.split == "test")
    active_encoder = encoder or FrozenResNet18Encoder(config.encoder_path, config.device)
    cached = load_or_create_features(config, samples, active_encoder)
    feature_by_path = {path: index for index, path in enumerate(cached.relative_paths)}

    def selected_features(selected: tuple[VisionSample, ...]) -> VisionFeatures:
        indices = [feature_by_path[_relative_path(config, sample)] for sample in selected]
        return VisionFeatures(
            cached.global_embeddings[indices],
            cached.patch_embeddings[indices],
        )

    fit_features = selected_features(fit_samples)
    calibration_features = selected_features(calibration_samples)
    test_features = selected_features(test_samples)

    global_detector = GlobalMahalanobisDetector().fit(fit_features.global_embeddings)
    global_calibration_scores = global_detector.anomaly_scores(
        calibration_features.global_embeddings
    )
    global_threshold = calibration_threshold(
        global_calibration_scores,
        config.image_threshold_percentile,
    )

    patch_detector = PatchNearestNeighborDetector(
        max_bank_size=config.patch_bank_max_size,
        random_seed=config.random_seed,
        image_score_percentile=config.image_score_percentile,
    ).fit(fit_features.patch_embeddings)
    calibration_patch_maps = patch_detector.patch_scores(calibration_features.patch_embeddings)
    calibration_image_scores = _image_scores(
        calibration_patch_maps,
        config.image_score_percentile,
    )
    image_threshold = calibration_threshold(
        calibration_image_scores,
        config.image_threshold_percentile,
    )
    canvas_size = active_encoder.metadata.preprocessing["canvas_size"]
    calibration_pixel_scores = np.concatenate(
        [
            resize_anomaly_map(anomaly_map, int(canvas_size)).reshape(-1)
            for anomaly_map in calibration_patch_maps
        ]
    )
    pixel_threshold = calibration_threshold(
        calibration_pixel_scores,
        config.pixel_threshold_percentile,
    )

    # The official test representations are scored once after all V1 choices and both
    # normal-only thresholds are frozen.
    labels = np.asarray([int(sample.is_anomaly) for sample in test_samples], dtype=np.int64)
    global_test_scores = global_detector.anomaly_scores(test_features.global_embeddings)
    test_patch_maps = patch_detector.patch_scores(test_features.patch_embeddings)
    patch_test_scores = _image_scores(test_patch_maps, config.image_score_percentile)
    upsampled_test_maps = np.stack(
        [resize_anomaly_map(anomaly_map, int(canvas_size)) for anomaly_map in test_patch_maps]
    )
    transformed_masks = np.stack(
        [_transformed_mask(sample, config, int(canvas_size)) for sample in test_samples]
    )

    global_evaluation = evaluate_image_scores(labels, global_test_scores, global_threshold)
    patch_evaluation = evaluate_image_scores(labels, patch_test_scores, image_threshold)
    localization_evaluation = evaluate_pixel_scores(
        transformed_masks,
        upsampled_test_maps,
        pixel_threshold,
    )

    preparation = json.loads((config.dataset_root / "preparation.json").read_text(encoding="utf-8"))
    split_sha256 = _sha256(config.official_split_path)
    audit = audit_dataset(samples, config)
    metadata = VisionArtifactMetadata(
        format_version=VISION_ARTIFACT_FORMAT_VERSION,
        dataset="VisA",
        dataset_source=VISA_SOURCE,
        dataset_license=VISA_LICENSE,
        dataset_archive_sha256=str(preparation["archive_sha256"]),
        subset="PCB1",
        supported_asset_types=SUPPORTED_ASSET_TYPES,
        official_split_identity={
            "file": "split_csv/1cls.csv",
            "sha256": split_sha256,
            "training_normal_count": 904,
            "test_normal_count": 100,
            "test_anomaly_count": 100,
            "fit_fraction": config.fit_fraction,
            "random_seed": config.random_seed,
            "fit_calibration_group_policy": "numeric filename ID // 10 acquisition block",
        },
        detector_fit_normal_count=len(fit_samples),
        calibration_normal_count=len(calibration_samples),
        test_normal_count=int(np.count_nonzero(labels == 0)),
        test_anomaly_count=int(np.count_nonzero(labels == 1)),
        encoder=active_encoder.metadata,
        patch_normalization="per-patch L2 normalization",
        patch_bank_sampling={
            "policy": "fixed-seed uniform sampling without replacement",
            "random_seed": config.random_seed,
            "maximum_size": config.patch_bank_max_size,
            "source": "detector-fit normal PCB1 patches only",
        },
        patch_bank_size=patch_detector.bank_size,
        distance_metric="cosine distance to nearest normal reference patch",
        image_score_rule=f"linear p{config.image_score_percentile * 100:g} patch distance",
        image_threshold_policy=(
            f"linear p{config.image_threshold_percentile * 100:g} of held-out normal "
            "calibration image scores"
        ),
        image_threshold_percentile=config.image_threshold_percentile,
        image_threshold=image_threshold,
        pixel_threshold_policy=(
            f"linear p{config.pixel_threshold_percentile * 100:g} of held-out normal "
            "calibration anomaly-map pixels"
        ),
        pixel_threshold_percentile=config.pixel_threshold_percentile,
        pixel_threshold=pixel_threshold,
        calibration_score_summary=score_summary(calibration_image_scores),
        global_evaluation_metrics=global_evaluation.to_dict(),
        patch_evaluation_metrics=patch_evaluation.to_dict(),
        localization_metrics=localization_evaluation.to_dict(),
        confidence_semantics=(
            "bounded RAW empirical anomaly/normal evidence relative to held-out normal "
            "calibration image scores; not probability, severity, health, or risk"
        ),
    )
    artifact = VisionModelArtifact(
        detector=patch_detector,
        normal_calibration_scores=tuple(float(value) for value in calibration_image_scores),
        metadata=metadata,
    )
    save_vision_artifact(artifact, config.artifact_path)
    config.artifact_path.with_suffix(".metadata.json").write_text(
        json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    results = _results_document(
        config=config,
        samples=samples,
        fit_samples=fit_samples,
        calibration_samples=calibration_samples,
        test_samples=test_samples,
        encoder=active_encoder,
        cached=cached,
        audit=audit,
        metadata=metadata,
        global_threshold=global_threshold,
        global_calibration_scores=global_calibration_scores,
        global_evaluation=global_evaluation,
        patch_evaluation=patch_evaluation,
        localization_evaluation=localization_evaluation,
        patch_test_scores=patch_test_scores,
        labels=labels,
        peak_memory=peak_memory,
    )
    config.evaluation_path.parent.mkdir(parents=True, exist_ok=True)
    config.evaluation_path.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return VisionTrainingOutcome(
        global_evaluation,
        patch_evaluation,
        localization_evaluation,
        str(config.artifact_path),
        str(config.evaluation_path),
    )


def load_or_create_features(
    config: VisionTrainingConfig,
    samples: tuple[VisionSample, ...],
    encoder: VisionFeatureEncoder,
) -> CachedVisionFeatures:
    relative_paths = tuple(_relative_path(config, sample) for sample in samples)
    if config.feature_cache_path.is_file():
        with np.load(config.feature_cache_path, allow_pickle=False) as cached:
            metadata = json.loads(str(cached["metadata"].item()))
            cached_paths = tuple(str(value) for value in cached["relative_paths"])
            current_metadata = json.loads(json.dumps(encoder.metadata.to_dict()))
            if metadata == current_metadata and cached_paths == relative_paths:
                features = VisionFeatures(
                    cached["global_embeddings"],
                    cached["patch_embeddings"],
                )
                validate_features(features, len(samples), encoder.metadata)
                return CachedVisionFeatures(
                    relative_paths,
                    features.global_embeddings,
                    features.patch_embeddings,
                    True,
                    0.0,
                )

    started = time.perf_counter()
    global_batches: list[NDArray[np.float64]] = []
    patch_batches: list[NDArray[np.float64]] = []
    for start in range(0, len(samples), config.batch_size):
        batch_samples = samples[start : start + config.batch_size]
        features = encoder.encode_batch(tuple(load_image(sample) for sample in batch_samples))
        validate_features(features, len(batch_samples), encoder.metadata)
        global_batches.append(features.global_embeddings)
        patch_batches.append(features.patch_embeddings)
        completed = min(start + config.batch_size, len(samples))
        if completed == len(samples) or completed % 100 < config.batch_size:
            print(f"ResNet-18 features: {completed}/{len(samples)}", flush=True)
    extraction_seconds = time.perf_counter() - started
    global_embeddings = np.vstack(global_batches).astype(np.float32)
    patch_embeddings = np.vstack(patch_batches).astype(np.float32)
    config.feature_cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        config.feature_cache_path,
        metadata=json.dumps(encoder.metadata.to_dict(), sort_keys=True),
        relative_paths=np.asarray(relative_paths),
        global_embeddings=global_embeddings,
        patch_embeddings=patch_embeddings,
    )
    return CachedVisionFeatures(
        relative_paths,
        global_embeddings,
        patch_embeddings,
        False,
        extraction_seconds,
    )


def audit_dataset(
    samples: tuple[VisionSample, ...],
    config: VisionTrainingConfig,
) -> dict[str, object]:
    resolutions: Counter[tuple[str, str, int, int]] = Counter()
    formats: Counter[str] = Counter()
    digest_paths: defaultdict[str, list[str]] = defaultdict(list)
    perceptual: list[tuple[str, str, int]] = []
    normal_thumbnails: list[tuple[int, NDArray[np.float32]]] = []
    for sample in samples:
        relative = _relative_path(config, sample)
        digest_paths[_sha256(sample.image_path)].append(relative)
        with Image.open(sample.image_path) as image:
            formats[str(image.format)] += 1
            resolutions[(sample.split, sample.label, image.width, image.height)] += 1
            grayscale = image.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
            values = np.asarray(grayscale, dtype=np.int16)
            bits = values[:, 1:] > values[:, :-1]
            perceptual_hash = sum(int(bit) << index for index, bit in enumerate(bits.flat))
            perceptual.append((sample.split, relative, perceptual_hash))
            if not sample.is_anomaly:
                thumbnail = (
                    np.asarray(
                        image.convert("L").resize((32, 24), Image.Resampling.BILINEAR),
                        dtype=np.float32,
                    )
                    / 255.0
                )
                normal_thumbnails.append((int(sample.image_path.stem), thumbnail))
    duplicate_groups = [paths for paths in digest_paths.values() if len(paths) > 1]
    split_duplicate_groups = [
        paths
        for paths in duplicate_groups
        if len(
            {
                next(sample.split for sample in samples if _relative_path(config, sample) == path)
                for path in paths
            }
        )
        > 1
    ]
    near_split_pairs = 0
    for index, (split, _, fingerprint) in enumerate(perceptual):
        for other_split, _, other_fingerprint in perceptual[index + 1 :]:
            if split != other_split and (fingerprint ^ other_fingerprint).bit_count() <= 1:
                near_split_pairs += 1
    normal_thumbnails.sort(key=lambda item: item[0])
    thumbnail_stack = np.stack([item[1] for item in normal_thumbnails])
    sequential_mae = np.mean(
        np.abs(thumbnail_stack[1:] - thumbnail_stack[:-1]),
        axis=(1, 2),
    )
    random = np.random.default_rng(config.random_seed)
    pair_indices = random.integers(0, len(thumbnail_stack), size=(5_000, 2))
    random_mae = np.mean(
        np.abs(thumbnail_stack[pair_indices[:, 0]] - thumbnail_stack[pair_indices[:, 1]]),
        axis=(1, 2),
    )
    return {
        "image_formats": dict(sorted(formats.items())),
        "image_resolution_distribution": [
            {
                "split": split,
                "label": label,
                "width": width,
                "height": height,
                "count": count,
            }
            for (split, label, width, height), count in sorted(resolutions.items())
        ],
        "exact_duplicate_image_groups": duplicate_groups,
        "exact_duplicate_groups_crossing_official_split": split_duplicate_groups,
        "near_duplicate_cross_split_pairs_dhash_hamming_le_1": near_split_pairs,
        "sequence_similarity_audit": {
            "method": "32x24 grayscale mean absolute difference",
            "sequential_median": float(np.median(sequential_mae)),
            "random_pair_median": float(np.median(random_mae)),
            "fit_calibration_mitigation": (
                "numeric filename acquisition blocks of ten are assigned wholly to fit or "
                "calibration"
            ),
        },
        "predictive_metadata_excluded": [
            "filesystem path",
            "filename",
            "directory label",
            "split",
            "normal/anomaly label",
            "anomaly class",
            "mask",
            "image metadata",
        ],
        "label_leakage_observation": (
            "directory names and official CSV reveal Normal/Anomaly and are used only for "
            "loading, splitting, and evaluation"
        ),
    }


def _results_document(
    *,
    config: VisionTrainingConfig,
    samples: tuple[VisionSample, ...],
    fit_samples: tuple[VisionSample, ...],
    calibration_samples: tuple[VisionSample, ...],
    test_samples: tuple[VisionSample, ...],
    encoder: VisionFeatureEncoder,
    cached: CachedVisionFeatures,
    audit: dict[str, object],
    metadata: VisionArtifactMetadata,
    global_threshold: float,
    global_calibration_scores: NDArray[np.float64],
    global_evaluation: VisionImageEvaluation,
    patch_evaluation: VisionImageEvaluation,
    localization_evaluation: VisionPixelEvaluation,
    patch_test_scores: NDArray[np.float64],
    labels: NDArray[np.int64],
    peak_memory: int,
) -> dict[str, object]:
    preparation = json.loads((config.dataset_root / "preparation.json").read_text("utf-8"))
    annotation = _annotation_summary(config.dataset_root)
    predictions = patch_test_scores > metadata.image_threshold
    examples: dict[str, dict[str, object] | None] = {}
    for name, matches in (
        ("true_positive", (labels == 1) & predictions),
        ("false_positive", (labels == 0) & predictions),
        ("false_negative", (labels == 1) & ~predictions),
    ):
        indices = np.flatnonzero(matches)
        examples[name] = (
            {
                "image": _relative_path(config, test_samples[int(indices[0])]),
                "image_score": float(patch_test_scores[int(indices[0])]),
            }
            if len(indices)
            else None
        )
    return {
        "experiment": {
            "name": "SentinelAI Vision Intelligence V1",
            "primary_runtime_method_predeclared": "patch_nearest_neighbor",
            "normal_only_detector_fitting": True,
            "test_set_evaluations": 1,
        },
        "dataset": {
            "name": "Visual Anomaly (VisA)",
            "source": VISA_SOURCE,
            "archive_url": VISA_ARCHIVE_URL,
            "archive_bytes": preparation["archive_bytes"],
            "archive_sha256": preparation["archive_sha256"],
            "license": VISA_LICENSE,
            "subset": "PCB1",
            "total_images": len(samples),
            "normal_images": sum(not sample.is_anomaly for sample in samples),
            "anomaly_images": sum(sample.is_anomaly for sample in samples),
            "mask_count": sum(sample.mask_path is not None for sample in samples),
            "annotation": annotation,
            **audit,
        },
        "split": {
            "official_file": "split_csv/1cls.csv",
            "official_file_sha256": _sha256(config.official_split_path),
            "official_training_normal_count": 904,
            "detector_fit_normal_count": len(fit_samples),
            "calibration_normal_count": len(calibration_samples),
            "test_normal_count": sum(not sample.is_anomaly for sample in test_samples),
            "test_anomaly_count": sum(sample.is_anomaly for sample in test_samples),
            "fit_fraction": config.fit_fraction,
            "random_seed": config.random_seed,
            "fit_calibration_group_policy": "numeric filename ID // 10 acquisition block",
            "anomalies_used_for_fitting_or_thresholds": 0,
            "masks_used_for_fitting_or_thresholds": 0,
        },
        "encoder": {
            **encoder.metadata.to_dict(),
            "frozen": True,
            "device": encoder.device,
            "classifier_logits_used": False,
        },
        "feature_cache": {
            "path": str(config.feature_cache_path),
            "cache_hit": cached.cache_hit,
            "extraction_seconds": cached.extraction_seconds,
            "image_count": len(cached.relative_paths),
        },
        "global_mahalanobis_comparison": {
            "role": "comparison only; not eligible to replace predeclared runtime method",
            "model": "StandardScaler then LedoitWolf Mahalanobis distance",
            "threshold": {
                "policy": "p99 held-out normal calibration image scores",
                "value": global_threshold,
                "summary": score_summary(global_calibration_scores),
            },
            "image_metrics": global_evaluation.to_dict(),
        },
        "patch_nearest_neighbor": {
            "role": "predeclared runtime method",
            "patch_normalization": metadata.patch_normalization,
            "memory_bank": metadata.patch_bank_sampling,
            "memory_bank_size": metadata.patch_bank_size,
            "distance_metric": metadata.distance_metric,
            "image_score_rule": metadata.image_score_rule,
            "image_threshold": {
                "policy": metadata.image_threshold_policy,
                "value": metadata.image_threshold,
                "normal_calibration_count": metadata.calibration_normal_count,
                "summary": metadata.calibration_score_summary,
            },
            "pixel_threshold": {
                "policy": metadata.pixel_threshold_policy,
                "value": metadata.pixel_threshold,
            },
            "image_metrics": patch_evaluation.to_dict(),
            "localization_metrics": localization_evaluation.to_dict(),
            "representative_examples": examples,
        },
        "artifact": {
            "path": str(config.artifact_path),
            "format_version": metadata.format_version,
            "bytes": config.artifact_path.stat().st_size,
            "encoder_stored_inside_artifact": False,
        },
        "runtime": {
            "device": encoder.device,
            "tracemalloc_peak_bytes": peak_memory,
            "resnet_weights_bytes": encoder.metadata.weights_bytes,
            "patch_memory_bank_bytes": int(
                metadata.patch_bank_size * metadata.encoder.patch_dimension * 4
            ),
        },
        "confidence": {
            "kind": "raw",
            "definition": metadata.confidence_semantics,
            "cross_modally_comparable": False,
        },
        "limitations": [
            "PCB1 reference distribution only",
            "visual_anomaly is not a precise mechanical fault diagnosis",
            "raw Vision confidence is not probability, severity, health, or operational risk",
            "no confidence calibration or multimodal fusion",
            "ImageNet features can shift under new cameras, lighting, views, or PCB variants",
            "localization is coarse at a 16x16 feature grid and is offline-only",
            "ResNet-18 deployment has not been measured on Raspberry Pi 4",
        ],
    }


def _transformed_mask(
    sample: VisionSample,
    config: VisionTrainingConfig,
    canvas_size: int,
) -> NDArray[np.uint8]:
    image = load_image(sample)
    _, geometry = preprocess_image(image, config.preprocessing)
    if geometry.canvas_size != canvas_size:
        raise ValueError("Training preprocessing does not match the prepared encoder")
    mask = load_mask(sample, image.pixels.shape[:2])
    return preprocess_mask(mask, geometry)


def _image_scores(
    patch_maps: NDArray[np.float64],
    percentile: float,
) -> NDArray[np.float64]:
    return np.quantile(
        patch_maps.reshape(len(patch_maps), -1),
        percentile,
        axis=1,
        method="linear",
    ).astype(np.float64, copy=False)


def _relative_path(config: VisionTrainingConfig, sample: VisionSample) -> str:
    return sample.image_path.relative_to(config.dataset_root.resolve()).as_posix()


def _annotation_summary(dataset_root: Path) -> dict[str, object]:
    files = tuple(dataset_root.rglob("pcb1/image_anno.csv"))
    if len(files) != 1:
        raise ValueError("Expected exactly one PCB1 image annotation file")
    import pandas as pd

    frame = pd.read_csv(files[0])
    class_columns = [
        name
        for name in frame.columns
        if "class" in name.lower() or "type" in name.lower() or "category" in name.lower()
    ]
    anomaly_labels = sorted(
        str(value) for value in frame.loc[frame["label"] != "normal", "label"].unique()
    )
    atomic_classes = sorted(
        {part.strip() for label in anomaly_labels for part in label.split(",") if part.strip()}
    )
    return {
        "file": files[0].relative_to(dataset_root).as_posix(),
        "columns": list(frame.columns),
        "rows": len(frame),
        "anomaly_class_columns": {
            name: sorted(str(value) for value in frame[name].dropna().unique())
            for name in class_columns
        },
        "anomaly_label_combinations": anomaly_labels,
        "anomaly_classes": atomic_classes,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
