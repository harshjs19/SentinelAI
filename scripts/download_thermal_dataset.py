import argparse
import hashlib
import json
import re
import shutil
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

DATASET_DOI = "doi:10.34810/DATA2500"
DATASET_VERSION = "2.1"
DATASET_API = (
    "https://dataverse.csuc.cat/api/datasets/:persistentId/versions/"
    f"{DATASET_VERSION}?persistentId={urllib.parse.quote(DATASET_DOI, safe='')}"
)
FILE_API = "https://dataverse.csuc.cat/api/access/datafile/{file_id}"
STATIONARY_MAT_PATTERN = re.compile(r"^(H|BD|HB|OB|U|M|W25|W50|W75)_F(5|15|50|60)_S\.mat$")
METADATA_FILENAMES = {
    "Readme.txt",
    "Information_about_database_files.txt",
    "Information_environmental_conditions.txt",
    "Sampling_frequency_and_units.txt",
}
EXPECTED_CONDITIONS = {"H", "BD", "HB", "OB", "U", "M", "W25", "W50", "W75"}
EXPECTED_SPEEDS = {"5", "15", "50", "60"}


@dataclass(frozen=True)
class SelectedFile:
    file_id: int
    filename: str
    file_size: int
    checksum_algorithm: str
    checksum: str

    def to_dict(self) -> dict[str, object]:
        return {
            "dataverse_file_id": self.file_id,
            "filename": self.filename,
            "file_size": self.file_size,
            "checksum_algorithm": self.checksum_algorithm,
            "checksum": self.checksum,
        }


def download_thermal_dataset(dataset_root: Path) -> dict[str, object]:
    metadata = _read_json(DATASET_API)
    if metadata.get("status") != "OK":
        raise RuntimeError("CORA Dataverse returned an unsuccessful dataset response")
    version = metadata["data"]
    actual_version = f"{version['versionNumber']}.{version['versionMinorNumber']}"
    if actual_version != DATASET_VERSION:
        raise ValueError(
            f"CORA dataset version mismatch: expected {DATASET_VERSION}, got {actual_version}"
        )

    selected = _select_files(version["files"])
    dataset_root.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as executor:
        downloads = {
            executor.submit(_verified_download, file, dataset_root / file.filename): file
            for file in selected
        }
        for download in as_completed(downloads):
            file = downloads[download]
            download.result()
            print(f"verified {file.filename} ({file.file_size} bytes)", flush=True)

    manifest = {
        "dataset_title": "Rotating electromechanical system dataset for condition monitoring",
        "persistent_id": DATASET_DOI,
        "dataset_version": DATASET_VERSION,
        "version_release_time": version["releaseTime"],
        "license": version["license"]["name"],
        "source": "CORA Research Data Repository",
        "api_url": DATASET_API,
        "selection": {
            "stationary_mat_pattern": STATIONARY_MAT_PATTERN.pattern,
            "stationary_mat_count": 36,
            "metadata_text_count": 4,
            "selected_file_count": len(selected),
            "selected_bytes": sum(file.file_size for file in selected),
        },
        "files": [file.to_dict() for file in selected],
    }
    manifest_path = dataset_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _select_files(files: list[dict[str, object]]) -> tuple[SelectedFile, ...]:
    selected: list[SelectedFile] = []
    experiments: set[tuple[str, str]] = set()
    metadata_names: set[str] = set()
    for entry in files:
        data_file = entry["dataFile"]
        filename = str(data_file["filename"])
        match = STATIONARY_MAT_PATTERN.fullmatch(filename)
        if match is None and filename not in METADATA_FILENAMES:
            continue
        checksum = data_file["checksum"]
        selected.append(
            SelectedFile(
                file_id=int(data_file["id"]),
                filename=filename,
                file_size=int(data_file["filesize"]),
                checksum_algorithm=str(checksum["type"]),
                checksum=str(checksum["value"]).lower(),
            )
        )
        if match is not None:
            experiments.add((match.group(1), match.group(2)))
        else:
            metadata_names.add(filename)

    expected_experiments = {
        (condition, speed) for condition in EXPECTED_CONDITIONS for speed in EXPECTED_SPEEDS
    }
    if experiments != expected_experiments:
        raise ValueError("Official metadata does not contain the expected 36 stationary MAT files")
    if metadata_names != METADATA_FILENAMES:
        raise ValueError("Official metadata does not contain the expected interpretation files")
    if len(selected) != 40 or len({file.filename for file in selected}) != 40:
        raise ValueError("Thermal subset selection must contain exactly 40 unique files")
    return tuple(sorted(selected, key=lambda file: file.filename.lower()))


def _verified_download(file: SelectedFile, destination: Path) -> None:
    if destination.is_file() and destination.stat().st_size == file.file_size:
        if _checksum(destination, file.checksum_algorithm) == file.checksum:
            return

    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        FILE_API.format(file_id=file.file_id),
        headers={"User-Agent": "SentinelAI thermal dataset downloader"},
    )
    try:
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            temporary.open("wb") as output,
        ):
            shutil.copyfileobj(response, output, length=1024 * 1024)
        if temporary.stat().st_size != file.file_size:
            raise ValueError(f"Downloaded file has an unexpected size: {file.filename}")
        if _checksum(temporary, file.checksum_algorithm) != file.checksum:
            raise ValueError(f"Downloaded file checksum does not match Dataverse: {file.filename}")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(url: str) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SentinelAI thermal dataset downloader"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError("CORA Dataverse returned malformed metadata")
    return result


def _checksum(path: Path, algorithm: str) -> str:
    normalized = algorithm.lower().replace("-", "")
    try:
        digest = hashlib.new(normalized)
    except ValueError as error:
        raise ValueError(f"Unsupported Dataverse checksum algorithm: {algorithm}") from error
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download the official CORA stationary thermography subset"
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("datasets/thermal_condition_monitoring"),
    )
    args = parser.parse_args()
    print(json.dumps(download_thermal_dataset(args.dataset_root), indent=2))


if __name__ == "__main__":
    main()
