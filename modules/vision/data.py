import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from modules.vision.input import VisionInput
from modules.vision.preprocessing import decode_image


@dataclass(frozen=True)
class VisionSample:
    image_path: Path
    mask_path: Path | None
    split: str
    label: str

    @property
    def is_anomaly(self) -> bool:
        return self.label == "anomaly"


def discover_pcb1_samples(
    dataset_root: Path,
    official_split_path: Path,
) -> tuple[VisionSample, ...]:
    if not official_split_path.is_file():
        raise FileNotFoundError("Official VisA one-class split CSV is missing")
    roots = [dataset_root, *sorted(path.parent for path in dataset_root.rglob("pcb1"))]
    rows: list[VisionSample] = []
    with official_split_path.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            if row["object"].lower() != "pcb1":
                continue
            relative_image = Path(row["image"])
            image_path = _resolve_relative_path(relative_image, roots)
            mask_value = row.get("mask", "").strip()
            mask_path = _resolve_relative_path(Path(mask_value), roots) if mask_value else None
            rows.append(VisionSample(image_path, mask_path, row["split"], row["label"]))
    samples = tuple(rows)
    counts = {
        ("train", "normal"): 904,
        ("test", "normal"): 100,
        ("test", "anomaly"): 100,
    }
    actual = {
        key: sum(sample.split == key[0] and sample.label == key[1] for sample in samples)
        for key in counts
    }
    if actual != counts:
        raise ValueError(f"Unexpected official VisA PCB1 split counts: {actual}")
    if any(sample.is_anomaly and sample.mask_path is None for sample in samples):
        raise ValueError("Official VisA PCB1 anomaly sample is missing a mask")
    return samples


def split_normal_training(
    samples: tuple[VisionSample, ...],
    fit_fraction: float,
    random_seed: int,
) -> tuple[tuple[VisionSample, ...], tuple[VisionSample, ...]]:
    if not 0 < fit_fraction < 1:
        raise ValueError("Vision fit fraction must be between zero and one")
    normals = tuple(
        sorted(
            (sample for sample in samples if sample.split == "train" and not sample.is_anomaly),
            key=lambda sample: sample.image_path.as_posix(),
        )
    )
    groups: dict[int, list[VisionSample]] = {}
    for sample in normals:
        try:
            acquisition_block = int(sample.image_path.stem) // 10
        except ValueError as error:
            raise ValueError("VisA PCB1 normal filenames must contain numeric image IDs") from error
        groups.setdefault(acquisition_block, []).append(sample)
    random = np.random.default_rng(random_seed)
    group_ids = tuple(sorted(groups))
    target_fit_count = int(len(normals) * fit_fraction)
    fit_group_ids: set[int] = set()
    current_count = 0
    for position in random.permutation(len(group_ids)):
        group_id = group_ids[int(position)]
        proposed_count = current_count + len(groups[group_id])
        if abs(target_fit_count - proposed_count) <= abs(target_fit_count - current_count):
            fit_group_ids.add(group_id)
            current_count = proposed_count
    fit = tuple(sample for group_id in sorted(fit_group_ids) for sample in groups[group_id])
    calibration = tuple(
        sample
        for group_id in group_ids
        if group_id not in fit_group_ids
        for sample in groups[group_id]
    )
    return fit, calibration


def load_image(sample: VisionSample) -> VisionInput:
    return decode_image(sample.image_path.read_bytes())


def load_mask(sample: VisionSample, expected_shape: tuple[int, int]) -> NDArray[np.uint8]:
    if sample.mask_path is None:
        return np.zeros(expected_shape, dtype=np.uint8)
    try:
        with Image.open(sample.mask_path) as image:
            image.load()
            mask = np.asarray(image.convert("L"), dtype=np.uint8)
    except OSError as error:
        raise ValueError("VisA PCB1 mask is unreadable") from error
    if mask.shape != expected_shape:
        raise ValueError("VisA PCB1 mask does not align with its source image")
    return (mask > 0).astype(np.uint8)


def _resolve_relative_path(relative: Path, roots: list[Path]) -> Path:
    matches = [root / relative for root in roots if (root / relative).is_file()]
    unique = tuple(dict.fromkeys(path.resolve() for path in matches))
    if len(unique) != 1:
        raise FileNotFoundError(f"Expected exactly one VisA file for {relative.as_posix()}")
    return unique[0]
