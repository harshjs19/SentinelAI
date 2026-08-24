import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.io import loadmat, whosmat
from scipy.io.matlab import MatReadError

from modules.thermal.config import CONDITION_LABELS, SPEED_RPM
from modules.thermal.input import ThermalInput

THERMAL_VARIABLE = "imagenes_celda"
EXPECTED_FRAME_COUNT = 450
EXPECTED_FRAME_SHAPE = (240, 320, 3)
_FILENAME_PATTERN = re.compile(r"^(H|BD|HB|OB|U|M|W25|W50|W75)_(F5|F15|F50|F60)_S\.mat$")


@dataclass(frozen=True)
class ThermalExperiment:
    path: Path
    raw_condition: str
    condition: str
    speed: str
    rpm: int

    @property
    def experiment_id(self) -> str:
        return self.path.stem


@dataclass(frozen=True)
class MatInspection:
    matlab_version: str
    variable_name: str
    variable_shape: tuple[int, ...]
    variable_type: str
    frame_count: int
    frame_shape: tuple[int, ...]
    frame_dtype: str


def discover_experiments(dataset_root: Path) -> tuple[ThermalExperiment, ...]:
    experiments = tuple(
        parse_experiment_path(path) for path in sorted(dataset_root.glob("*_F*_S.mat"))
    )
    expected = len(CONDITION_LABELS) * len(SPEED_RPM)
    if len(experiments) != expected:
        raise ValueError(
            f"Expected {expected} stationary thermal experiments, got {len(experiments)}"
        )
    identities = {(item.raw_condition, item.speed) for item in experiments}
    if len(identities) != expected:
        raise ValueError("Stationary thermal experiment identities are not unique")
    return experiments


def parse_experiment_path(path: Path) -> ThermalExperiment:
    match = _FILENAME_PATTERN.fullmatch(path.name)
    if match is None:
        raise ValueError(f"Invalid stationary thermal filename: {path.name}")
    raw_condition, speed = match.groups()
    return ThermalExperiment(
        path=path.resolve(),
        raw_condition=raw_condition,
        condition=CONDITION_LABELS[raw_condition],
        speed=speed,
        rpm=SPEED_RPM[speed],
    )


def inspect_mat(path: Path) -> MatInspection:
    variables = whosmat(path)
    thermal = [item for item in variables if item[0] == THERMAL_VARIABLE]
    if len(thermal) != 1:
        raise ValueError(f"MAT file must contain the {THERMAL_VARIABLE} thermal variable")
    variable_name, variable_shape, variable_type = thermal[0]
    frames = load_thermal_frames(path)
    header = path.read_bytes()[:128]
    if not header.startswith(b"MATLAB 5.0 MAT-file"):
        raise ValueError("Thermal dataset MAT file must use MATLAB 5 format")
    return MatInspection(
        matlab_version="MATLAB 5.0",
        variable_name=variable_name,
        variable_shape=tuple(variable_shape),
        variable_type=variable_type,
        frame_count=len(frames),
        frame_shape=tuple(frames[0].pixels.shape),
        frame_dtype=str(frames[0].pixels.dtype),
    )


def load_thermal_frames(path: Path) -> tuple[ThermalInput, ...]:
    try:
        content = loadmat(
            path,
            variable_names=[THERMAL_VARIABLE],
            squeeze_me=False,
            struct_as_record=False,
            verify_compressed_data_integrity=True,
        )
    except (MatReadError, OSError, ValueError, TypeError) as error:
        raise ValueError("Thermal MAT file is unreadable or corrupt") from error
    if THERMAL_VARIABLE not in content:
        raise ValueError(f"MAT file must contain the {THERMAL_VARIABLE} thermal variable")
    cells = np.asarray(content[THERMAL_VARIABLE], dtype=object).reshape(-1)
    if not len(cells):
        raise ValueError("Thermal MAT file contains no frames")
    frames: list[ThermalInput] = []
    for index, frame in enumerate(cells, start=1):
        if not isinstance(frame, np.ndarray):
            raise ValueError(f"Thermal frame {index} is not an image matrix")
        if frame.shape != EXPECTED_FRAME_SHAPE or frame.dtype != np.uint8:
            raise ValueError(
                f"Thermal frame {index} must have shape {EXPECTED_FRAME_SHAPE} and dtype uint8"
            )
        frames.append(ThermalInput(np.ascontiguousarray(frame)))
    return tuple(frames)


def frame_sha256(frame: ThermalInput) -> str:
    return hashlib.sha256(frame.pixels.tobytes(order="C")).hexdigest()
