from pathlib import Path

import numpy as np
import pytest
from scipy.io import savemat

from modules.thermal.data import (
    EXPECTED_FRAME_SHAPE,
    THERMAL_VARIABLE,
    inspect_mat,
    load_thermal_frames,
    parse_experiment_path,
)


def write_mat(path: Path, frames: list[np.ndarray], variable: str = THERMAL_VARIABLE) -> None:
    cells = np.empty((1, len(frames)), dtype=object)
    for index, frame in enumerate(frames):
        cells[0, index] = frame
    savemat(path, {variable: cells}, do_compression=True)


def thermal_frame(value: int = 20) -> np.ndarray:
    return np.full(EXPECTED_FRAME_SHAPE, value, dtype=np.uint8)


def test_loads_discovered_mat_cell_array_and_preserves_frame_order(tmp_path: Path) -> None:
    path = tmp_path / "H_F5_S.mat"
    write_mat(path, [thermal_frame(11), thermal_frame(22)])

    inspection = inspect_mat(path)
    frames = load_thermal_frames(path)

    assert inspection.matlab_version == "MATLAB 5.0"
    assert inspection.variable_name == THERMAL_VARIABLE
    assert inspection.variable_shape == (1, 2)
    assert inspection.variable_type == "cell"
    assert inspection.frame_shape == EXPECTED_FRAME_SHAPE
    assert inspection.frame_dtype == "uint8"
    assert [int(frame.pixels[0, 0, 0]) for frame in frames] == [11, 22]


def test_rejects_unreadable_mat(tmp_path: Path) -> None:
    path = tmp_path / "H_F5_S.mat"
    path.write_bytes(b"not-a-mat-file")

    with pytest.raises(ValueError, match="unreadable or corrupt"):
        load_thermal_frames(path)


def test_rejects_missing_thermal_variable(tmp_path: Path) -> None:
    path = tmp_path / "H_F5_S.mat"
    write_mat(path, [thermal_frame()], variable="wrong_variable")

    with pytest.raises(ValueError, match=THERMAL_VARIABLE):
        load_thermal_frames(path)


@pytest.mark.parametrize(
    "frame",
    [
        np.zeros((240, 320), dtype=np.uint8),
        np.zeros(EXPECTED_FRAME_SHAPE, dtype=np.float32),
        np.zeros((224, 224, 3), dtype=np.uint8),
    ],
)
def test_rejects_malformed_thermal_frame(tmp_path: Path, frame: np.ndarray) -> None:
    path = tmp_path / "H_F5_S.mat"
    write_mat(path, [frame])

    with pytest.raises(ValueError, match="frame 1"):
        load_thermal_frames(path)


@pytest.mark.parametrize(
    ("filename", "raw_condition", "condition", "speed", "rpm"),
    [
        ("H_F5_S.mat", "H", "healthy", "F5", 300),
        ("BD_F15_S.mat", "BD", "bearing_fault", "F15", 900),
        ("HB_F50_S.mat", "HB", "half_broken_rotor_bar", "F50", 3000),
        ("OB_F60_S.mat", "OB", "broken_rotor_bar", "F60", 3600),
        ("U_F5_S.mat", "U", "imbalance", "F5", 300),
        ("M_F5_S.mat", "M", "misalignment", "F5", 300),
        ("W75_F60_S.mat", "W75", "gear_wear_75", "F60", 3600),
    ],
)
def test_parses_condition_and_operating_speed_metadata(
    tmp_path: Path,
    filename: str,
    raw_condition: str,
    condition: str,
    speed: str,
    rpm: int,
) -> None:
    experiment = parse_experiment_path(tmp_path / filename)

    assert experiment.raw_condition == raw_condition
    assert experiment.condition == condition
    assert experiment.speed == speed
    assert experiment.rpm == rpm


def test_rejects_filename_outside_stationary_experiment_contract(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="filename"):
        parse_experiment_path(tmp_path / "healthy_300rpm.mat")
