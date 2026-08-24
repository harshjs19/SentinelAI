import json
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from modules.thermal.config import DATASET_DOI, DATASET_VERSION
from modules.thermal.data import (
    EXPECTED_FRAME_COUNT,
    ThermalExperiment,
    discover_experiments,
    frame_sha256,
    load_thermal_frames,
)
from modules.thermal.encoder import ThermalFeatureEncoder, validate_embeddings


@dataclass(frozen=True)
class ThermalEmbeddingData:
    embeddings: NDArray[np.float64]
    labels: NDArray[np.str_]
    raw_conditions: NDArray[np.str_]
    speeds: NDArray[np.str_]
    rpms: NDArray[np.int64]
    experiment_ids: NDArray[np.str_]
    relative_files: NDArray[np.str_]
    frame_indices: NDArray[np.int64]
    audit: dict[str, object]
    cache_hit: bool
    extraction_seconds: float


def load_or_extract_embeddings(
    dataset_root: Path,
    cache_path: Path,
    encoder: ThermalFeatureEncoder,
    batch_size: int,
) -> ThermalEmbeddingData:
    if batch_size <= 0:
        raise ValueError("Thermal encoder batch size must be positive")
    manifest = _load_manifest(dataset_root)
    experiments = discover_experiments(dataset_root)
    identity = _cache_identity(manifest, experiments, encoder)
    if cache_path.is_file():
        cached = _load_cache(cache_path, identity)
        if cached is not None:
            reports = cached.audit.get("file_reports", [])
            if any("exact_duplicate_frames" not in report for report in reports):
                cached = replace(
                    cached,
                    audit=_augment_file_duplicate_reports(cached.audit, experiments),
                )
                _save_cache(cache_path, identity, cached)
            return cached

    start = time.perf_counter()
    embedding_batches: list[NDArray[np.float64]] = []
    labels: list[str] = []
    raw_conditions: list[str] = []
    speeds: list[str] = []
    rpms: list[int] = []
    experiment_ids: list[str] = []
    relative_files: list[str] = []
    frame_indices: list[int] = []
    file_reports: list[dict[str, object]] = []
    hash_locations: dict[str, list[tuple[str, str, str]]] = {}
    experiment_hashes: dict[str, list[str]] = {}
    adjacent_near_duplicate_pairs = 0
    adjacent_pair_count = 0
    replicated_grayscale_frames = 0

    for experiment in experiments:
        frames = load_thermal_frames(experiment.path)
        relative_file = experiment.path.relative_to(dataset_root.resolve()).as_posix()
        file_reports.append(
            {
                "experiment_id": experiment.experiment_id,
                "filename": relative_file,
                "condition": experiment.condition,
                "raw_condition": experiment.raw_condition,
                "speed": experiment.speed,
                "rpm": experiment.rpm,
                "expected_frames": EXPECTED_FRAME_COUNT,
                "actual_frames": len(frames),
                "missing_frames": max(0, EXPECTED_FRAME_COUNT - len(frames)),
                "corrupt_frames": 0,
            }
        )
        previous: NDArray[np.uint8] | None = None
        experiment_hashes[experiment.experiment_id] = []
        for index, frame in enumerate(frames, start=1):
            digest = frame_sha256(frame)
            experiment_hashes[experiment.experiment_id].append(digest)
            hash_locations.setdefault(digest, []).append(
                (experiment.experiment_id, experiment.condition, experiment.speed)
            )
            pixels = frame.pixels
            if np.array_equal(pixels[..., 0], pixels[..., 1]) and np.array_equal(
                pixels[..., 1], pixels[..., 2]
            ):
                replicated_grayscale_frames += 1
            if previous is not None:
                adjacent_pair_count += 1
                mean_absolute_difference = float(
                    np.abs(pixels.astype(np.int16) - previous.astype(np.int16)).mean()
                )
                if mean_absolute_difference <= 1.0:
                    adjacent_near_duplicate_pairs += 1
            previous = pixels
            labels.append(experiment.condition)
            raw_conditions.append(experiment.raw_condition)
            speeds.append(experiment.speed)
            rpms.append(experiment.rpm)
            experiment_ids.append(experiment.experiment_id)
            relative_files.append(relative_file)
            frame_indices.append(index)

        for start_index in range(0, len(frames), batch_size):
            batch = frames[start_index : start_index + batch_size]
            embeddings = encoder.encode_batch(batch)
            validate_embeddings(embeddings, len(batch), encoder.metadata.global_dimension)
            embedding_batches.append(embeddings.astype(np.float64, copy=False))

    duplicate_groups = [locations for locations in hash_locations.values() if len(locations) > 1]
    duplicate_digests = {
        digest for digest, locations in hash_locations.items() if len(locations) > 1
    }
    cross_experiment_digests = {
        digest
        for digest, locations in hash_locations.items()
        if len({location[0] for location in locations}) > 1
    }
    for report in file_reports:
        hashes = experiment_hashes[str(report["experiment_id"])]
        report["exact_duplicate_frames"] = sum(digest in duplicate_digests for digest in hashes)
        report["within_experiment_duplicate_occurrences"] = len(hashes) - len(set(hashes))
        report["cross_experiment_duplicate_frames"] = sum(
            digest in cross_experiment_digests for digest in hashes
        )
    audit = {
        "expected_frames_per_experiment": EXPECTED_FRAME_COUNT,
        "file_reports": file_reports,
        "total_frames": len(labels),
        "missing_frames": sum(int(report["missing_frames"]) for report in file_reports),
        "corrupt_frames": 0,
        "unique_frame_matrices": len(hash_locations),
        "exact_duplicate_frame_occurrences": sum(len(group) - 1 for group in duplicate_groups),
        "exact_duplicate_groups": len(duplicate_groups),
        "duplicate_groups_spanning_experiments": sum(
            len({location[0] for location in group}) > 1 for group in duplicate_groups
        ),
        "duplicate_groups_spanning_conditions": sum(
            len({location[1] for location in group}) > 1 for group in duplicate_groups
        ),
        "duplicate_groups_spanning_speeds": sum(
            len({location[2] for location in group}) > 1 for group in duplicate_groups
        ),
        "adjacent_pair_count": adjacent_pair_count,
        "adjacent_near_duplicate_threshold": "mean absolute uint8 difference <= 1.0",
        "adjacent_near_duplicate_pairs": adjacent_near_duplicate_pairs,
        "replicated_grayscale_frames": replicated_grayscale_frames,
        "rendered_overlay_review": (
            "Sampled real frames contain no filename, condition code, temperature scale, "
            "timestamp, or class-label overlay"
        ),
        "predictive_metadata": "pixels only; filenames, condition codes, and speed excluded",
    }
    data = ThermalEmbeddingData(
        embeddings=np.concatenate(embedding_batches, axis=0),
        labels=np.asarray(labels, dtype=np.str_),
        raw_conditions=np.asarray(raw_conditions, dtype=np.str_),
        speeds=np.asarray(speeds, dtype=np.str_),
        rpms=np.asarray(rpms, dtype=np.int64),
        experiment_ids=np.asarray(experiment_ids, dtype=np.str_),
        relative_files=np.asarray(relative_files, dtype=np.str_),
        frame_indices=np.asarray(frame_indices, dtype=np.int64),
        audit=audit,
        cache_hit=False,
        extraction_seconds=time.perf_counter() - start,
    )
    _validate_data(data, encoder.metadata.global_dimension)
    _save_cache(cache_path, identity, data)
    return data


def _cache_identity(
    manifest: dict[str, object],
    experiments: tuple[ThermalExperiment, ...],
    encoder: ThermalFeatureEncoder,
) -> dict[str, object]:
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list):
        raise ValueError("Thermal dataset manifest is missing file identities")
    mat_names = {experiment.path.name for experiment in experiments}
    files = [file for file in manifest_files if file.get("filename") in mat_names]
    if len(files) != len(experiments):
        raise ValueError("Thermal dataset manifest does not cover all MAT experiments")
    return {
        "dataset_doi": DATASET_DOI,
        "dataset_version": DATASET_VERSION,
        "dataset_files": sorted(files, key=lambda file: str(file["filename"])),
        "preprocessing": encoder.metadata.preprocessing,
        "encoder": encoder.metadata.to_dict(),
        "embedding_dimension": encoder.metadata.global_dimension,
    }


def _load_manifest(dataset_root: Path) -> dict[str, object]:
    path = dataset_root / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        raise ValueError("Thermal dataset manifest is missing or invalid") from error
    if (
        manifest.get("persistent_id") != DATASET_DOI
        or manifest.get("dataset_version") != DATASET_VERSION
    ):
        raise ValueError("Thermal dataset manifest identity does not match the pinned dataset")
    return manifest


def _save_cache(
    path: Path,
    identity: dict[str, object],
    data: ThermalEmbeddingData,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        identity=np.asarray(json.dumps(identity, sort_keys=True)),
        audit=np.asarray(json.dumps(data.audit, sort_keys=True)),
        extraction_seconds=np.asarray(data.extraction_seconds, dtype=np.float64),
        embeddings=data.embeddings.astype(np.float32),
        labels=data.labels,
        raw_conditions=data.raw_conditions,
        speeds=data.speeds,
        rpms=data.rpms,
        experiment_ids=data.experiment_ids,
        relative_files=data.relative_files,
        frame_indices=data.frame_indices,
    )


def _load_cache(
    path: Path,
    identity: dict[str, object],
) -> ThermalEmbeddingData | None:
    try:
        with np.load(path, allow_pickle=False) as cached:
            if str(cached["identity"].item()) != json.dumps(identity, sort_keys=True):
                return None
            data = ThermalEmbeddingData(
                embeddings=np.asarray(cached["embeddings"], dtype=np.float64),
                labels=np.asarray(cached["labels"], dtype=np.str_),
                raw_conditions=np.asarray(cached["raw_conditions"], dtype=np.str_),
                speeds=np.asarray(cached["speeds"], dtype=np.str_),
                rpms=np.asarray(cached["rpms"], dtype=np.int64),
                experiment_ids=np.asarray(cached["experiment_ids"], dtype=np.str_),
                relative_files=np.asarray(cached["relative_files"], dtype=np.str_),
                frame_indices=np.asarray(cached["frame_indices"], dtype=np.int64),
                audit=json.loads(str(cached["audit"].item())),
                cache_hit=True,
                extraction_seconds=float(cached["extraction_seconds"].item()),
            )
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None
    _validate_data(data, int(identity["embedding_dimension"]))
    return data


def _validate_data(data: ThermalEmbeddingData, embedding_dimension: int) -> None:
    rows = len(data.labels)
    validate_embeddings(data.embeddings, rows, embedding_dimension)
    aligned = (
        data.raw_conditions,
        data.speeds,
        data.rpms,
        data.experiment_ids,
        data.relative_files,
        data.frame_indices,
    )
    if any(len(values) != rows for values in aligned):
        raise ValueError("Thermal embedding-cache metadata is not frame-aligned")


def _augment_file_duplicate_reports(
    audit: dict[str, object],
    experiments: tuple[ThermalExperiment, ...],
) -> dict[str, object]:
    hash_locations: dict[str, list[str]] = {}
    experiment_hashes: dict[str, list[str]] = {}
    for experiment in experiments:
        hashes = [frame_sha256(frame) for frame in load_thermal_frames(experiment.path)]
        experiment_hashes[experiment.experiment_id] = hashes
        for digest in hashes:
            hash_locations.setdefault(digest, []).append(experiment.experiment_id)
    duplicate_digests = {
        digest for digest, locations in hash_locations.items() if len(locations) > 1
    }
    cross_experiment_digests = {
        digest for digest, locations in hash_locations.items() if len(set(locations)) > 1
    }
    updated = dict(audit)
    reports: list[dict[str, object]] = []
    for original in audit["file_reports"]:  # type: ignore[index]
        report = dict(original)
        hashes = experiment_hashes[str(report["experiment_id"])]
        report["exact_duplicate_frames"] = sum(digest in duplicate_digests for digest in hashes)
        report["within_experiment_duplicate_occurrences"] = len(hashes) - len(set(hashes))
        report["cross_experiment_duplicate_frames"] = sum(
            digest in cross_experiment_digests for digest in hashes
        )
        reports.append(report)
    updated["file_reports"] = reports
    return updated
