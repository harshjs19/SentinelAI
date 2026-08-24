import argparse
import hashlib
import json
import math
import re
import shutil
import statistics
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATASET_DOI = "doi:10.34810/DATA2500"
DATASET_VERSION = "2.1"
DATASET_TITLE = "Rotating electromechanical system dataset for condition monitoring"
DATASET_API = (
    "https://dataverse.csuc.cat/api/datasets/:persistentId/versions/"
    f"{DATASET_VERSION}?persistentId={urllib.parse.quote(DATASET_DOI, safe='')}"
)
FILE_API = "https://dataverse.csuc.cat/api/access/datafile/{file_id}?format=original"
FILE_DDI_API = "https://dataverse.csuc.cat/api/access/datafile/{file_id}/metadata/ddi"
CONDITIONS = ("H", "BD", "HB", "OB", "U", "M", "W25", "W50", "W75")
SPEEDS = ("F5", "F15", "F50", "F60")
REPRESENTATIVE_EXPERIMENTS = ("H_F5_S", "BD_F15_S", "W75_F50_S")
REPRESENTATIVE_CHANNELS = ("Vx", "Vy", "Vz", "C1", "T1", "RPM")
_TIMING_PATTERN = re.compile(
    r"^(?P<condition>H|BD|HB|OB|U|M|W25|W50|W75)_"
    r"(?P<speed>F5|F15|F50|F60)_(?P<regime>S|T)_"
    r"Time(?P<modality>Cu|Vi|Temp|RPM|Vo|IR)\.(?:csv|tab)$",
    re.IGNORECASE,
)
_F60_EXPERIMENT_PAYLOAD_PATTERN = re.compile(
    r"^(?:H|BD|HB|OB|U|M|W25|W50|W75)_F60_(?:S|T)(?:_|\.)",
    re.IGNORECASE,
)
_ALIGNMENT_TERM_PATTERNS = {
    "time": re.compile(r"time", re.IGNORECASE),
    "timestamp": re.compile(r"timestamp", re.IGNORECASE),
    "IR": re.compile(r"(?:^|[^a-z0-9])ir(?:[^a-z0-9]|$)", re.IGNORECASE),
    "thermal/thermography": re.compile(r"therm(?:al|ograph)", re.IGNORECASE),
    "camera": re.compile(r"camera", re.IGNORECASE),
    "Vi": re.compile(r"(?:^|_)vi(?:_|\.|$)|timevi", re.IGNORECASE),
    "vibration": re.compile(r"vibration", re.IGNORECASE),
    "RPM": re.compile(r"rpm", re.IGNORECASE),
    "synchronization/sync": re.compile(r"sync|synchron", re.IGNORECASE),
    "start": re.compile(r"start", re.IGNORECASE),
    "trigger": re.compile(r"trigger", re.IGNORECASE),
    "sampling": re.compile(r"sampling", re.IGNORECASE),
    "clock": re.compile(r"clock", re.IGNORECASE),
}


@dataclass(frozen=True)
class ManifestFile:
    file_id: int
    stored_filename: str
    original_filename: str | None
    stored_size: int
    original_size: int | None
    checksum_algorithm: str
    checksum: str
    content_type: str
    directory: str | None
    description: str | None

    @classmethod
    def from_dataverse(cls, entry: dict[str, Any]) -> "ManifestFile":
        data_file = entry["dataFile"]
        checksum = data_file["checksum"]
        return cls(
            file_id=int(data_file["id"]),
            stored_filename=str(data_file["filename"]),
            original_filename=_optional_string(data_file.get("originalFileName")),
            stored_size=int(data_file["filesize"]),
            original_size=_optional_int(data_file.get("originalFileSize")),
            checksum_algorithm=str(checksum["type"]),
            checksum=str(checksum["value"]).lower(),
            content_type=str(data_file["contentType"]),
            directory=_optional_string(entry.get("directoryLabel")),
            description=_optional_string(entry.get("description")),
        )

    @property
    def effective_filename(self) -> str:
        return self.original_filename or self.stored_filename

    def to_dict(self) -> dict[str, object]:
        return {
            "dataverse_file_id": self.file_id,
            "filename": self.effective_filename,
            "stored_filename": self.stored_filename,
            "directory": self.directory,
            "stored_size": self.stored_size,
            "original_size": self.original_size,
            "checksum_algorithm": self.checksum_algorithm,
            "checksum": self.checksum,
            "description": self.description,
            "content_type": self.content_type,
            "metadata_url": f"https://dataverse.csuc.cat/api/files/{self.file_id}",
        }


@dataclass(frozen=True)
class DatasetManifest:
    title: str
    persistent_id: str
    release_time: str
    license_name: str
    files: tuple[ManifestFile, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_title": self.title,
            "persistent_id": self.persistent_id,
            "dataset_version": DATASET_VERSION,
            "version_release_time": self.release_time,
            "license": self.license_name,
            "api_url": DATASET_API,
            "file_count": len(self.files),
            "files": [file.to_dict() for file in self.files],
        }


@dataclass(frozen=True)
class TimingFile:
    file: ManifestFile
    experiment_id: str
    condition: str
    speed: str
    regime: str
    modality: str

    def to_dict(self) -> dict[str, object]:
        return {
            **self.file.to_dict(),
            "experiment_id": self.experiment_id,
            "condition": self.condition,
            "speed": self.speed,
            "regime": self.regime,
            "timing_modality": self.modality,
        }


def parse_version_manifest(payload: dict[str, Any]) -> DatasetManifest:
    if payload.get("status") != "OK":
        raise RuntimeError("CORA Dataverse returned an unsuccessful dataset response")
    version = payload["data"]
    actual_version = f"{version['versionNumber']}.{version['versionMinorNumber']}"
    if actual_version != DATASET_VERSION:
        raise ValueError(
            f"CORA dataset version mismatch: expected {DATASET_VERSION}, got {actual_version}"
        )
    persistent_id = str(version["datasetPersistentId"])
    if persistent_id.casefold() != DATASET_DOI.casefold():
        raise ValueError(
            f"CORA dataset identity mismatch: expected {DATASET_DOI}, got {persistent_id}"
        )
    title_fields = [
        field
        for field in version["metadataBlocks"]["citation"]["fields"]
        if field.get("typeName") == "title"
    ]
    if len(title_fields) != 1 or str(title_fields[0]["value"]) != DATASET_TITLE:
        raise ValueError("CORA dataset title is missing or does not match the pinned dataset")
    files = tuple(
        sorted(
            (ManifestFile.from_dataverse(entry) for entry in version["files"]),
            key=lambda file: (file.effective_filename.lower(), file.file_id),
        )
    )
    if len({file.file_id for file in files}) != len(files):
        raise ValueError("CORA manifest contains duplicate Dataverse file IDs")
    return DatasetManifest(
        title=DATASET_TITLE,
        persistent_id=persistent_id,
        release_time=str(version["releaseTime"]),
        license_name=str(version["license"]["name"]),
        files=files,
    )


def classify_timing_file(file: ManifestFile) -> TimingFile | None:
    match = _TIMING_PATTERN.fullmatch(file.effective_filename)
    if match is None:
        return None
    condition = match.group("condition").upper()
    speed = match.group("speed").upper()
    regime = match.group("regime").upper()
    return TimingFile(
        file=file,
        experiment_id=f"{condition}_{speed}_{regime}",
        condition=condition,
        speed=speed,
        regime=regime,
        modality=match.group("modality"),
    )


def find_timing_files(files: tuple[ManifestFile, ...]) -> tuple[TimingFile, ...]:
    timing_files = (classify_timing_file(file) for file in files)
    return tuple(item for item in timing_files if item is not None)


def find_alignment_candidates(files: tuple[ManifestFile, ...]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for file in files:
        searchable_metadata = " ".join(
            value
            for value in (
                file.stored_filename,
                file.original_filename,
                file.directory,
                file.description,
                file.content_type,
            )
            if value is not None
        )
        matched_terms = sorted(
            term
            for term, pattern in _ALIGNMENT_TERM_PATTERNS.items()
            if pattern.search(searchable_metadata)
        )
        if matched_terms:
            candidates.append({**file.to_dict(), "matched_terms": matched_terms})
    return candidates


def ensure_payload_inspection_allowed(filename: str) -> None:
    if _F60_EXPERIMENT_PAYLOAD_PATTERN.match(filename):
        raise ValueError("F60 experiment payload inspection is forbidden during CORA Gate 0")


def ensure_file_payload_inspection_allowed(file: ManifestFile) -> None:
    ensure_payload_inspection_allowed(file.stored_filename)
    if file.original_filename is not None:
        ensure_payload_inspection_allowed(file.original_filename)


def validate_timing_vector(values: list[float]) -> dict[str, float | int]:
    if len(values) < 2:
        raise ValueError("Timing vector must contain at least two values")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Timing vector must contain only finite values")
    differences = [current - previous for previous, current in zip(values, values[1:])]
    if any(difference <= 0.0 for difference in differences):
        raise ValueError("Timing vector must be strictly increasing")
    return {
        "value_count": len(values),
        "first_value": values[0],
        "last_value": values[-1],
        "duration": values[-1] - values[0],
        "minimum_increment": min(differences),
        "median_increment": statistics.median(differences),
        "maximum_increment": max(differences),
    }


def alignment_blockers(
    files: tuple[ManifestFile, ...],
    *,
    common_time_origin_documented: bool,
    start_offset_documented: bool,
    clock_relationship_documented: bool,
) -> tuple[str, ...]:
    expected_stationary = {f"{condition}_{speed}_S" for condition in CONDITIONS for speed in SPEEDS}
    timing_files = find_timing_files(files)
    vibration_coverage = {
        item.experiment_id
        for item in timing_files
        if item.regime == "S" and item.modality.lower() == "vi"
    }
    thermal_coverage = {
        item.experiment_id
        for item in timing_files
        if item.regime == "S" and item.modality.lower() == "ir"
    }
    blockers: list[str] = []
    if vibration_coverage != expected_stationary:
        blockers.append("stationary vibration timing vectors do not cover all 36 experiments")
    if thermal_coverage != expected_stationary:
        blockers.append("thermal capture timestamps do not cover all 36 experiments")
    if not common_time_origin_documented:
        blockers.append("a common thermal/DAS time origin is not documented")
    if not start_offset_documented:
        blockers.append("the first thermal capture offset relative to vibration is not documented")
    if not clock_relationship_documented:
        blockers.append("the camera/DAS clock relationship and drift handling are not documented")
    return tuple(blockers)


def audit_manifest(manifest: DatasetManifest) -> dict[str, object]:
    timing_files = find_timing_files(manifest.files)
    alignment_candidates = find_alignment_candidates(manifest.files)
    coverage: dict[str, list[str]] = {}
    for item in timing_files:
        coverage.setdefault(item.experiment_id, []).append(item.modality)
    time_ir_exists = any(item.modality.lower() == "ir" for item in timing_files)
    blockers = alignment_blockers(
        manifest.files,
        common_time_origin_documented=False,
        start_offset_documented=False,
        clock_relationship_documented=False,
    )
    return {
        "total_file_count": len(manifest.files),
        "timing_file_count": len(timing_files),
        "timing_files": [item.to_dict() for item in timing_files],
        "timing_coverage": {
            experiment: sorted(modalities) for experiment, modalities in sorted(coverage.items())
        },
        "time_ir_exists": time_ir_exists,
        "stationary_experiments_with_any_timing_file": sorted(
            experiment for experiment in coverage if experiment.endswith("_S")
        ),
        "f60_timing_files_metadata_only": [
            item.file.effective_filename for item in timing_files if item.speed == "F60"
        ],
        "exact_alignment_reproducible": not blockers,
        "alignment_blockers": list(blockers),
        "alignment_metadata_search": {
            "searched_fields": [
                "stored filename",
                "original filename",
                "directory",
                "description",
                "content type",
            ],
            "searched_terms": list(_ALIGNMENT_TERM_PATTERNS),
            "candidate_count": len(alignment_candidates),
            "term_counts": {
                term: sum(term in candidate["matched_terms"] for candidate in alignment_candidates)
                for term in _ALIGNMENT_TERM_PATTERNS
            },
            "candidates": alignment_candidates,
        },
    }


def download_non_f60_timing_files(
    timing_files: tuple[TimingFile, ...], destination: Path
) -> list[dict[str, object]]:
    destination.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, object]] = []
    for timing_file in timing_files:
        if timing_file.speed == "F60":
            continue
        path = destination / timing_file.file.effective_filename
        _download_original(timing_file.file, path)
        values = _read_numeric_vector(path)
        summaries.append(
            {
                **timing_file.to_dict(),
                "local_filename": path.name,
                "local_sha256": _checksum(path, "sha256"),
                "download_validation": (
                    "original byte size and Dataverse manifest MD5 both matched; local SHA-256 "
                    "is supplementary"
                ),
                "layout": {"numeric_columns": 1, "header_rows": 0},
                "inspection": validate_timing_vector(values),
            }
        )
    return summaries


def inspect_representative_file_metadata(
    files: tuple[ManifestFile, ...], destination: Path
) -> list[dict[str, object]]:
    by_name = {file.effective_filename: file for file in files}
    expected_names = [
        f"{experiment}_{channel}.csv"
        for experiment in REPRESENTATIVE_EXPERIMENTS
        for channel in REPRESENTATIVE_CHANNELS
    ]
    missing = sorted(set(expected_names) - set(by_name))
    if missing:
        raise ValueError(f"Representative CORA files are missing: {missing}")
    destination.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, object]] = []
    for filename in expected_names:
        file = by_name[filename]
        ensure_file_payload_inspection_allowed(file)
        content = _read_bytes(FILE_DDI_API.format(file_id=file.file_id))
        parsed_metadata = parse_file_ddi(content, file)
        local_path = destination / f"{Path(filename).stem}.ddi.xml"
        local_path.write_bytes(content)
        summaries.append(
            {
                **file.to_dict(),
                **parsed_metadata,
                "ddi_url": FILE_DDI_API.format(file_id=file.file_id),
                "local_ddi_filename": local_path.name,
                "local_ddi_sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return summaries


def parse_file_ddi(content: bytes, file: ManifestFile) -> dict[str, object]:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise ValueError(f"Malformed DDI metadata for {file.effective_filename}") from error
    file_description = root.find(".//{*}fileDscr")
    filename = root.findtext(".//{*}fileDscr/{*}fileTxt/{*}fileName")
    case_quantity = root.findtext(".//{*}fileDscr/{*}fileTxt/{*}dimensns/{*}caseQnty")
    variable_quantity = root.findtext(".//{*}fileDscr/{*}fileTxt/{*}dimensns/{*}varQnty")
    dataset_identifier = root.findtext(".//{*}stdyDscr/{*}citation/{*}titlStmt/{*}IDNo")
    variables = root.findall(".//{*}dataDscr/{*}var")
    if (
        file_description is None
        or file_description.get("ID") != f"f{file.file_id}"
        or filename != file.stored_filename
        or case_quantity is None
        or variable_quantity is None
        or dataset_identifier is None
        or f"doi:{dataset_identifier}".casefold() != DATASET_DOI.casefold()
    ):
        raise ValueError(f"DDI metadata identity mismatch for {file.effective_filename}")
    numeric_variable_name = len(variables) == 1 and _is_float(variables[0].get("name"))
    cases = int(case_quantity)
    return {
        "ddi_case_quantity": cases,
        "ddi_variable_quantity": int(variable_quantity),
        "numeric_variable_name": numeric_variable_name,
        "inferred_original_numeric_value_count": cases + 1 if numeric_variable_name else cases,
    }


def _download_original(file: ManifestFile, destination: Path) -> None:
    ensure_file_payload_inspection_allowed(file)
    expected_size = file.original_size or file.stored_size
    if destination.is_file() and destination.stat().st_size == expected_size:
        if _checksum(destination, file.checksum_algorithm) == file.checksum:
            return
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        FILE_API.format(file_id=file.file_id),
        headers={"User-Agent": "SentinelAI CORA Gate 0 alignment audit"},
    )
    try:
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            temporary.open("wb") as output,
        ):
            shutil.copyfileobj(response, output, length=1024 * 1024)
        if temporary.stat().st_size != expected_size:
            raise ValueError(f"Downloaded file has an unexpected size: {file.effective_filename}")
        if _checksum(temporary, file.checksum_algorithm) != file.checksum:
            raise ValueError(f"Downloaded checksum does not match: {file.effective_filename}")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_numeric_vector(path: Path) -> list[float]:
    values: list[float] = []
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            fields = re.split(r"[,\t]", stripped)
            if len(fields) != 1:
                raise ValueError(
                    f"Timing vector must contain exactly one column at line {line_number}"
                )
            first_field = fields[0].strip().strip('"')
            try:
                values.append(float(first_field))
            except ValueError as error:
                raise ValueError(
                    f"Timing vector contains a non-numeric value at line {line_number}"
                ) from error
    return values


def _read_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SentinelAI CORA Gate 0 alignment audit"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError("CORA Dataverse returned malformed metadata")
    return result


def _read_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SentinelAI CORA Gate 0 alignment audit"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _checksum(path: Path, algorithm: str) -> str:
    normalized = algorithm.lower().replace("-", "")
    try:
        digest = hashlib.new(normalized)
    except ValueError as error:
        raise ValueError(f"Unsupported Dataverse checksum algorithm: {algorithm}") from error
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _is_float(value: str | None) -> bool:
    if value is None:
        return False
    try:
        float(value)
    except ValueError:
        return False
    return True


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit CORA v2.1 metadata for reproducible thermal/vibration alignment"
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("datasets/cora_alignment_gate0"),
    )
    parser.add_argument(
        "--download-non-f60-timing",
        action="store_true",
        help="Download and structurally inspect only timing files outside F60",
    )
    parser.add_argument(
        "--inspect-representative-metadata",
        action="store_true",
        help="Save file-level DDI counts for three non-F60 stationary experiments",
    )
    args = parser.parse_args()

    manifest = parse_version_manifest(_read_json(DATASET_API))
    args.output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_root / "dataverse_v2_1_manifest.json"
    _write_json(manifest_path, manifest.to_dict())

    audit = audit_manifest(manifest)
    timing_files = find_timing_files(manifest.files)
    downloaded: list[dict[str, object]] = []
    if args.download_non_f60_timing:
        downloaded = download_non_f60_timing_files(timing_files, args.output_root / "timing")
    representative_metadata: list[dict[str, object]] = []
    if args.inspect_representative_metadata:
        representative_metadata = inspect_representative_file_metadata(
            manifest.files, args.output_root / "metadata" / "ddi"
        )
    summary = {
        "dataset_doi": DATASET_DOI,
        "dataset_version": DATASET_VERSION,
        "official_manifest": DATASET_API,
        "audit": audit,
        "downloaded_non_f60_timing_files": downloaded,
        "downloaded_timing_bytes": sum(
            int(item["original_size"] or item["stored_size"]) for item in downloaded
        ),
        "representative_non_f60_file_metadata": representative_metadata,
        "f60_exclusion": {
            "manifest_metadata_inspected": True,
            "f60_file_level_ddi_metadata_fetched": False,
            "signal_or_timing_payload_downloaded": False,
            "guard": "all F60 experiment payload inspection is rejected before data access",
        },
        "evidence_status": "partial",
        "gate_status": "blocked",
        "gate_outcome": "partial",
        "gate_label": "PARTIAL / BLOCKED",
        "exact_thermal_to_vibration_mapping_reproducible": False,
    }
    summary_path = args.output_root / "inspection_summary.json"
    _write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
