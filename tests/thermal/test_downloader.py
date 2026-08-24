import pytest

from scripts.download_thermal_dataset import (
    EXPECTED_CONDITIONS,
    EXPECTED_SPEEDS,
    METADATA_FILENAMES,
    _select_files,
)


def dataverse_entry(file_id: int, filename: str, size: int = 10) -> dict[str, object]:
    return {
        "dataFile": {
            "id": file_id,
            "filename": filename,
            "filesize": size,
            "checksum": {"type": "MD5", "value": "abc"},
        }
    }


def official_file_listing() -> list[dict[str, object]]:
    files = [
        dataverse_entry(index, f"{condition}_F{speed}_S.mat")
        for index, (condition, speed) in enumerate(
            ((condition, speed) for condition in EXPECTED_CONDITIONS for speed in EXPECTED_SPEEDS),
            start=1,
        )
    ]
    files.extend(
        dataverse_entry(100 + index, filename, size=1)
        for index, filename in enumerate(METADATA_FILENAMES)
    )
    files.append(dataverse_entry(999, "H_F5_S_Vx.csv", size=38_000_000_000))
    return files


def test_selects_only_36_stationary_mat_and_four_metadata_files() -> None:
    selected = _select_files(official_file_listing())

    assert len(selected) == 40
    assert sum(file.filename.endswith(".mat") for file in selected) == 36
    assert {file.filename for file in selected if file.filename.endswith(".txt")} == (
        METADATA_FILENAMES
    )
    assert "H_F5_S_Vx.csv" not in {file.filename for file in selected}


def test_rejects_incomplete_stationary_matrix() -> None:
    files = official_file_listing()
    files = [entry for entry in files if entry["dataFile"]["filename"] != "H_F5_S.mat"]  # type: ignore[index]

    with pytest.raises(ValueError, match="36 stationary"):
        _select_files(files)
